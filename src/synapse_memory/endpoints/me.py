"""me endpoints — 사용자 voice/data로 결과 생성하는 클론 모드.

- draft_resume      : 회사 맞춤 이력서
- what_did_i_think  : 주제 회상 (세컨드 브레인, 시간순)
- decide            : 의사결정 코파일럿 (Profile + DecisionPatterns + RAG)

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import calendar
import contextlib
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from synapse_memory.cards.company import CompanyCard, load_company_card
from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.endpoints.postprocess import strip_meta_prefix
from synapse_memory.llm import claude as claude_api
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.rag import (
    VectorStore,
    embed_query,
    open_vector_store,
)
from synapse_memory.rag.indexer import company_card_to_text
from synapse_memory.storage.last_response import (
    AnswerCitation,
    new_answer_reference,
    save_last_answer,
)

DEFAULT_PROJECTS_FOR_RESUME = 6
DEFAULT_RESUME_MODEL = "sonnet"
DEFAULT_RESUME_TIMEOUT = 240
DRAFTS_SUBPATH = Path("30_Creative") / "Drafts"

RESUME_SYSTEM = """당신은 한국 IT 채용 시장에 능숙한 이력서 작성 어시스턴트입니다.

# 임무
지원 회사 정보(CompanyCard)와 사용자 ProjectCard 목록을 받아, **그 회사에 최적화된**
한국어 이력서를 markdown 형식으로 작성합니다.

# 원칙 (절대 위반 금지)
- 회사 키워드와 매칭되는 프로젝트를 **상단**에 배치
- 각 프로젝트의 메트릭/수치는 자료에 있는 값만 그대로 인용
- 자료에 없는 사실은 **추측 금지** — 누락 처리 또는 "정보 없음"
- 모든 주장에 ``[card_id]`` 출처 인용
- 출력 첫 문자는 ``-`` (frontmatter 시작). prose 앞부분 금지.

# 출력 형식
---
title: <display_name> 지원 이력서
company_id: <company_id>
position: <포지션 또는 빈 문자열>
generated: <YYYY-MM-DD>
based_on:
  - card_project:<id>
  - ...
---

# 핵심 한 줄 소개
회사 키워드를 반영한 1-2문장.

## 핵심 경험 (회사 매칭 우선)
- **<프로젝트>**: 회사 키워드 맞춘 한 줄 [card_id]
- ...

## 프로젝트 상세 (3-5개)

### <프로젝트명> ([card_id])
- **역할/기간**: ...
- **문제**: ...
- **접근**: ...
- **영향**: <수치 인용>
- **기술 스택**: ...

(반복)

## 기술 스택
회사 키워드와 매칭되는 항목 우선. 카테고리별 정리.

## 비고
자료에 없는 항목은 표시 안 함. 마지막에 "이력서 검토 후 본인이 채울 부분" 섹션 추가.
"""


@dataclass
class ResumeDraft:
    company_id: str
    company_name: str
    saved_path: Path
    project_card_ids: list[str] = field(default_factory=list)
    raw_text: str = ""


def _company_search_query(company: CompanyCard) -> str:
    """CompanyCard에서 매칭 query 문자열 추출."""
    parts: list[str] = [company.display_name]
    for p in company.positions:
        parts.append(p.title)
        if p.seniority:
            parts.append(p.seniority)
        parts.extend(p.keywords)
    if company.notes:
        parts.append(company.notes[:300])
    if company.body:
        parts.append(company.body[:500])
    return " ".join(parts)


def _build_resume_prompt(
    company: CompanyCard,
    matched: list[tuple],
) -> str:
    """CompanyCard + 매칭 ProjectCard들로 Claude user prompt 빌드."""
    company_block = company_card_to_text(company)
    project_blocks: list[str] = []
    for rec, dist in matched:
        cid = rec.metadata.get("card_id") or rec.id
        project_blocks.append(
            f"---\n[{cid}] (유사도 거리={dist:.3f})\n{rec.document}"
        )

    return (
        f"# 지원 회사\n{company_block}\n\n"
        f"# 사용자 ProjectCard ({len(matched)}개, 가까운 순)\n"
        + "\n\n".join(project_blocks)
        + "\n\n# 지시\n위 자료로 회사 맞춤 한국어 이력서를 작성하세요. "
        f"오늘 날짜: {datetime.date.today().isoformat()}."
    )


def draft_resume(
    company_id: str,
    *,
    top_k_projects: int = DEFAULT_PROJECTS_FOR_RESUME,
    model: str = DEFAULT_RESUME_MODEL,
    vault_path: Path | None = None,
    claude_env: ClaudeEnvironment | None = None,
    store: VectorStore | None = None,
    timeout: int = DEFAULT_RESUME_TIMEOUT,
) -> ResumeDraft:
    """회사 맞춤 이력서 자동 생성 → vault에 markdown 저장.

    Args:
        company_id: ``20_Reference/Companies/<id>.md`` 파일명 슬러그.
        top_k_projects: 매칭 ProjectCard 수 (이력서에 인용).
        model: Claude 모델 (sonnet 권장).

    Returns:
        ResumeDraft (저장 경로, 인용 project_ids, 원문).

    Raises:
        FileNotFoundError: CompanyCard 없음.
        ClaudeError: 호출 실패.
        ValueError: 매칭 ProjectCard 0건.
    """
    company = load_company_card(company_id, vault_path=vault_path)

    # RAG search — project만
    store = store or open_vector_store()
    query = _company_search_query(company)
    q_vec = embed_query(query)
    matched = store.query(
        q_vec,
        top_k=top_k_projects,
        where={"source_kind": "card_project"},
    )
    if not matched:
        raise ValueError(
            "매칭 ProjectCard 0건 — `synapse-memory rag index` 먼저 실행"
        )

    project_ids = [rec.metadata.get("card_id") or rec.id for rec, _ in matched]

    user_prompt = _build_resume_prompt(company, matched)

    raw_text = claude_api.complete(
        user_prompt,
        system=RESUME_SYSTEM,
        model=model,
        env=claude_env,
        timeout=timeout,
    )

    # vault에 저장
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    drafts_dir = vault / DRAFTS_SUBPATH
    drafts_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    safe_name = company.display_name.replace("/", "-").replace("\\", "-")
    filename = f"Resume - {safe_name} ({today[:7]}).md"
    path = drafts_dir / filename
    path.write_text(raw_text, encoding="utf-8")

    return ResumeDraft(
        company_id=company_id,
        company_name=company.display_name,
        saved_path=path,
        project_card_ids=project_ids,
        raw_text=raw_text,
    )


# ---------------------------------------------------------------------------
# what_did_i_think — 주제 회상 (세컨드 브레인)
# ---------------------------------------------------------------------------


WHAT_DID_I_THINK_SYSTEM = """당신은 사용자의 세컨드 브레인입니다.

# 임무
주어진 주제에 대해 사용자가 어떻게 생각해왔는지 **시간순 또는 입장별로** 정리.

# 원칙
- 사고 변화가 발견되면 명시 ("처음엔 X, 나중엔 Y").
- 입장 유지 시 "일관되게 X" 명시.
- 자료에 없으면 "자료 없음"으로 솔직히.
- 각 주장에 ``[card_id]`` 인용.
- 한국어, 간결.

# 형식
첫 줄: 핵심 한 문장. 그 다음 자세한 정리."""


@dataclass
class WhatDidIThinkResult:
    topic: str
    answer: str
    source_ids: list[str] = field(default_factory=list)


def what_did_i_think(
    topic: str,
    *,
    top_k: int = 8,
    model: str = "sonnet",
    claude_env: ClaudeEnvironment | None = None,
    store: VectorStore | None = None,
    by: Literal["time", "distance"] = "distance",
    limit: int = 20,
    today: datetime.date | None = None,
) -> WhatDidIThinkResult:
    """주제에 대한 과거 사고 회상.

    Parameters
    ----------
    by:
        ``"distance"`` (기본) — 기존 cosine 정렬 + Claude 정리 답변.
        ``"time"`` — period_end desc 시간순 정렬 + 분기 그룹 (외부 LLM 미호출,
        FR-A1 / specs/002-timeline-recall).
    limit:
        ``by="time"`` 모드에서 출력 카드 최대 수 (기본 20).
    today:
        ``by="time"`` 의 today_fallback 계산용. ``None`` 이면 ``datetime.date.today()``.
    """
    if not topic.strip():
        raise ValueError("topic은 빈 문자열일 수 없음")

    store = store or open_vector_store()
    q_vec = embed_query(topic)
    results = store.query(q_vec, top_k=top_k)

    if not results:
        if by == "time":
            return WhatDidIThinkResult(
                topic=topic,
                answer=_EMPTY_MESSAGE,
                source_ids=[],
            )
        return WhatDidIThinkResult(
            topic=topic,
            answer="자료 없음 — `synapse-memory rag index` 먼저",
            source_ids=[],
        )

    if by == "time":
        today_resolved = today or datetime.date.today()
        cards = [
            _resolve_sort_ts(
                dict(rec.metadata),
                today_resolved,
                distance=dist,
                document=rec.document,
            )
            for rec, dist in results
        ]
        sorted_cards = _sort_by_time(cards)
        groups = _group_by_quarter(sorted_cards)
        fallback = [c for c in sorted_cards if c.sort_ts_source == "no_time_meta"]
        markdown = _format_timeline_output(groups, limit=limit, fallback_items=fallback)
        source_ids = [c.card_id for c in sorted_cards[:limit] if c.card_id]
        _record_last_answer(
            command="me.what_did_i_think",
            query=topic,
            source_ids=source_ids,
        )
        return WhatDidIThinkResult(topic=topic, answer=markdown, source_ids=source_ids)

    parts: list[str] = []
    source_ids = []
    for rec, dist in results:
        cid = rec.metadata.get("card_id") or rec.id
        kind = rec.metadata.get("source_kind", "?")
        parts.append(
            f"---\n[{cid}] ({kind}, 거리={dist:.3f})\n{rec.document[:1500]}"
        )
        source_ids.append(cid)

    prompt = (
        f"# 주제\n{topic}\n\n"
        f"# 자료 (top {len(results)})\n"
        + "\n\n".join(parts)
        + "\n\n사용자가 이 주제에 대해 어떻게 생각해왔는지 정리."
    )

    answer = claude_api.complete(
        prompt,
        system=WHAT_DID_I_THINK_SYSTEM,
        model=model,
        env=claude_env,
        timeout=120,
    )
    answer = strip_meta_prefix(answer)
    _record_last_answer(
        command="me.what_did_i_think",
        query=topic,
        source_ids=source_ids,
    )
    return WhatDidIThinkResult(topic=topic, answer=answer, source_ids=source_ids)


# ---------------------------------------------------------------------------
# decide — 의사결정 코파일럿
# ---------------------------------------------------------------------------


DECIDE_SYSTEM = """당신은 사용자의 의사결정 코파일럿입니다.

# 임무
주어진 상황에 대해 **사용자라면 어떻게 결정할지** 추천.
사용자 Profile, DecisionPatterns, 관련 Card를 종합해서 답.

# 형식
1. **추천**: 한 줄로 명확히
2. **근거**: Profile/Patterns/Card 인용 (``[source]`` 형식)
3. **대안**: 1-2개 + 트레이드오프
4. **추가 고려**: 사용자가 자체 판단할 부분

# 원칙
- Profile/Patterns가 있으면 **반드시 그것 기반으로** 추천 (사용자 voice).
- 자료가 부족하면 솔직히 "추가 정보 필요" 명시.
- 외부 일반론 X — 사용자 자료만."""


@dataclass
class DecideResult:
    situation: str
    answer: str
    profile_used: bool
    source_ids: list[str] = field(default_factory=list)


def _load_profile_text(vault_path: Path | None = None) -> str:
    """vault Profile.md + DecisionPatterns.md → 단일 텍스트. 없으면 빈 문자열."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    parts: list[str] = []
    for fname in ("Profile.md", "DecisionPatterns.md", "DecisionQualityRegistry.md"):
        p = vault / "90_System" / "AI" / fname
        if p.is_file():
            try:
                parts.append(f"--- {fname} ---\n{p.read_text(encoding='utf-8')[:5000]}")
            except OSError:
                continue
    return "\n\n".join(parts)


def decide(
    situation: str,
    *,
    top_k: int = 6,
    model: str = "sonnet",
    claude_env: ClaudeEnvironment | None = None,
    store: VectorStore | None = None,
    vault_path: Path | None = None,
) -> DecideResult:
    """의사결정 코파일럿."""
    if not situation.strip():
        raise ValueError("situation은 빈 문자열일 수 없음")

    profile_text = _load_profile_text(vault_path)
    profile_used = bool(profile_text)

    store = store or open_vector_store()
    q_vec = embed_query(situation)
    results = store.query(q_vec, top_k=top_k)

    card_blocks: list[str] = []
    source_ids: list[str] = []
    for rec, dist in results:
        cid = rec.metadata.get("card_id") or rec.id
        card_blocks.append(
            f"---\n[{cid}] (거리={dist:.3f})\n{rec.document[:1200]}"
        )
        source_ids.append(cid)

    sections = [f"# 의사결정 상황\n{situation}"]
    if profile_text:
        sections.append(f"# 사용자 Profile (90_System/AI/)\n{profile_text}")
    else:
        sections.append(
            "# 사용자 Profile\n(없음 — `me update-profile`로 만든 뒤 진실원본으로 promote 필요)"
        )
    if card_blocks:
        sections.append("# 관련 Card\n" + "\n\n".join(card_blocks))
    else:
        sections.append("# 관련 Card\n(매칭 없음)")
    sections.append("# 지시\n위 자료로 사용자 voice 기반 추천.")
    prompt = "\n\n".join(sections)

    answer = claude_api.complete(
        prompt,
        system=DECIDE_SYSTEM,
        model=model,
        env=claude_env,
        timeout=120,
    )
    answer = strip_meta_prefix(answer)
    _record_last_answer(
        command="me.decide",
        query=situation,
        source_ids=source_ids,
    )
    return DecideResult(
        situation=situation,
        answer=answer,
        profile_used=profile_used,
        source_ids=source_ids,
    )


def _record_last_answer(
    *,
    command: str,
    query: str,
    source_ids: list[str],
) -> None:
    citations = tuple(
        AnswerCitation(
            target_kind="card",
            target_ref=source_id,
            source_kind="card",
            display_name=source_id,
        )
        for source_id in source_ids
    )
    ref = new_answer_reference(
        command=command,  # type: ignore[arg-type]
        query=query,
        citations=citations,
    )
    with contextlib.suppress(OSError, ValueError):
        save_last_answer(ref)


# ---------------------------------------------------------------------------
# Timeline recall (FR-A1, specs/002-timeline-recall) — module-private types
# ---------------------------------------------------------------------------
#
# 본 섹션은 ``me what-did-i-think --timeline`` 의 시간축 정렬·분기 그룹화
# 출력에 사용되는 transient 객체와 헬퍼 stub 을 정의한다.
#
# - data-model: specs/002-timeline-recall/data-model.md
# - contracts:  specs/002-timeline-recall/contracts/cli-contracts.md
# - research:   specs/002-timeline-recall/research.md (RT-1~RT-5)
#
# 모든 정렬·그룹화 결과는 stateless · in-memory only · 디스크 영구 저장 없음 (FR-015).


_SortTsSource = Literal[
    "period_end",
    "today_fallback",
    "created",
    "last_reviewed",
    "no_time_meta",
]


@dataclass(frozen=True)
class CardWithMeta:
    """Transient — retrieve 1건당 1개 생성, 정렬·그룹화·출력의 캐리어.

    data-model.md §1 의 schema 와 1:1 일치.
    """

    card_id: str
    display_name: str
    source_kind: Literal["card_project", "card_company"]
    sort_ts: datetime.datetime
    sort_ts_source: _SortTsSource
    created_ts: datetime.datetime
    distance: float | None
    citation_text: str
    body_redacted: str


@dataclass(frozen=True)
class TimelineGroup:
    """Transient — 같은 (year, quarter) 의 ``CardWithMeta`` 묶음.

    data-model.md §2 와 1:1 일치. ``months_present`` 는 FR-007 의 월 서브헤더
    트리거 (분기 내 ≥2 카드이면서 등장 월이 ≥2 일 때 출력).
    """

    quarter_label: str  # 예: "2024 Q3"
    year: int
    quarter: int  # 1~4
    sort_ts: datetime.datetime
    members: tuple[CardWithMeta, ...]
    months_present: tuple[int, ...]


# --- private helpers (T018~T021 implementations) ------------------------------


_DT_MIN = datetime.datetime(datetime.MINYEAR, 1, 1)


def _parse_iso_or_yyyymm(s: str | None) -> datetime.date | None:
    """``YYYY-MM-DD`` 또는 ``YYYY-MM`` 문자열 → ``date`` (RT-2 월 말일 정규화).

    실패 시 ``None`` 반환 (예외 없음, BT-4).
    """
    if not s or not isinstance(s, str):
        return None
    parts = s.split("-")
    try:
        if len(parts) == 3:
            return datetime.date.fromisoformat(s)
        if len(parts) == 2:
            year = int(parts[0])
            month = int(parts[1])
            last_day = calendar.monthrange(year, month)[1]
            return datetime.date(year, month, last_day)
    except (ValueError, TypeError):
        return None
    return None


def _to_dt(d: datetime.date | None) -> datetime.datetime:
    """``date`` → ``datetime`` (00:00:00). None 은 ``datetime.MINYEAR`` 폴백."""
    if d is None:
        return _DT_MIN
    return datetime.datetime.combine(d, datetime.time.min)


def _resolve_sort_ts(
    metadata: dict[str, str],
    today: datetime.date,
    *,
    distance: float | None = None,
    document: str = "",
) -> CardWithMeta:
    """ChromaDB metadata + today → ``CardWithMeta`` (RT-1 폴백, RT-2 YYYY-MM 정규화)."""
    card_id = str(metadata.get("card_id") or metadata.get("id") or "")
    raw_kind = str(metadata.get("source_kind") or "card_project")
    source_kind: Literal["card_project", "card_company"] = (
        "card_company" if raw_kind == "card_company" else "card_project"
    )
    display_name = str(metadata.get("display_name") or card_id)

    period_end = _parse_iso_or_yyyymm(metadata.get("period_end") or None)
    created = _parse_iso_or_yyyymm(metadata.get("created") or None)
    last_reviewed = _parse_iso_or_yyyymm(metadata.get("last_reviewed") or None)
    status = str(metadata.get("status") or "")

    sort_ts: datetime.datetime
    sort_ts_source: _SortTsSource

    if source_kind == "card_project":
        if period_end is not None:
            sort_ts = _to_dt(period_end)
            sort_ts_source = "period_end"
        elif status == "active":
            sort_ts = _to_dt(today)
            sort_ts_source = "today_fallback"
        elif created is not None:
            sort_ts = _to_dt(created)
            sort_ts_source = "created"
        else:
            sort_ts = _DT_MIN
            sort_ts_source = "no_time_meta"
    else:  # card_company
        if last_reviewed is not None:
            sort_ts = _to_dt(last_reviewed)
            sort_ts_source = "last_reviewed"
        elif created is not None:
            sort_ts = _to_dt(created)
            sort_ts_source = "created"
        else:
            sort_ts = _DT_MIN
            sort_ts_source = "no_time_meta"

    created_ts = _to_dt(created) if created is not None else _DT_MIN
    citation_text = f"[{source_kind}:{card_id}]"
    body_redacted = document or ""

    return CardWithMeta(
        card_id=card_id,
        display_name=display_name,
        source_kind=source_kind,
        sort_ts=sort_ts,
        sort_ts_source=sort_ts_source,
        created_ts=created_ts,
        distance=distance,
        citation_text=citation_text,
        body_redacted=body_redacted,
    )


def _sort_by_time(items: list[CardWithMeta]) -> list[CardWithMeta]:
    """``(sort_ts desc, created_ts desc)`` stable sort — research §BT-1."""
    return sorted(items, key=lambda c: (c.sort_ts, c.created_ts), reverse=True)


_QUARTER_OF_MONTH = {m: (m - 1) // 3 + 1 for m in range(1, 13)}


def _group_by_quarter(items: list[CardWithMeta]) -> list[TimelineGroup]:
    """정렬된 ``CardWithMeta`` 리스트를 (year, quarter) 그룹으로 묶음.

    ``no_time_meta`` 항목은 그룹에 포함하지 않음 (caller 가 fallback 으로 처리).
    그룹 자체의 순서는 입력 순서 (= sort_ts desc) 를 보존 (FR-006).
    """
    groups: list[TimelineGroup] = []
    current_key: tuple[int, int] | None = None
    current_members: list[CardWithMeta] = []

    def _close_group() -> None:
        if current_members and current_key is not None:
            year, quarter = current_key
            months = tuple(sorted({c.sort_ts.month for c in current_members}, reverse=True))
            groups.append(
                TimelineGroup(
                    quarter_label=f"{year} Q{quarter}",
                    year=year,
                    quarter=quarter,
                    sort_ts=current_members[0].sort_ts,
                    members=tuple(current_members),
                    months_present=months,
                )
            )

    for card in items:
        if card.sort_ts_source == "no_time_meta":
            continue
        year = card.sort_ts.year
        quarter = _QUARTER_OF_MONTH[card.sort_ts.month]
        key = (year, quarter)
        if current_key != key:
            _close_group()
            current_key = key
            current_members = []
        current_members.append(card)
    _close_group()

    return groups


def _label_for(card: CardWithMeta) -> str:
    """sort_ts_source → contract §"출력 라벨 매핑" 의 라벨 문자열."""
    if card.sort_ts_source == "period_end":
        return ""
    if card.sort_ts_source == "today_fallback":
        return f"(오늘 {card.sort_ts.date().isoformat()})"
    if card.sort_ts_source == "created":
        return "(created)"
    if card.sort_ts_source == "last_reviewed":
        return "(last reviewed)"
    return ""


def _render_card_line(card: CardWithMeta) -> str:
    """단일 카드 markdown 라인 — contract 의 출력 포맷.

    ``- **<id>** (<name>) — <date> <label>\n  > <body>\n  [<src>:<id>]``
    """
    date_str = card.sort_ts.date().isoformat()
    label = _label_for(card)
    suffix = f" {label}" if label else ""
    head = f"- **{card.card_id}** ({card.display_name}) — {date_str}{suffix}"
    body = card.body_redacted.strip().splitlines()[0] if card.body_redacted.strip() else ""
    if len(body) > 200:
        body = body[:200].rstrip() + "..."
    body_line = f"  > {body}" if body else ""
    citation = f"  {card.citation_text}"
    parts = [head]
    if body_line:
        parts.append(body_line)
    parts.append(citation)
    return "\n".join(parts)


_EMPTY_MESSAGE = "관련 카드 없음. `synapse-memory daily` 로 vault 수집을 다시 확인하세요."
_FALLBACK_HEADER = "## 시간 정보 없음 — distance 순 폴백"


def _format_timeline_output(
    groups: list[TimelineGroup],
    limit: int,
    *,
    fallback_items: list[CardWithMeta] | None = None,
) -> str:
    """contracts/cli-contracts.md §"Stdout 출력 — --timeline ON" 포맷 준수.

    - groups·fallback_items 모두 비어있으면 RT-5 의 0건 메시지.
    - 카드 1개 이하이고 fallback 없으면 그룹 헤더 생략 (FR-008).
    - 같은 분기 안 ≥2 카드 + 다른 월 ≥2 → 월 서브헤더 출력 (FR-007).
    - 끝에 ``총 N개 카드 (--limit M)`` footer (단, 단일 카드 케이스에는 생략).
    """
    fallback_items = fallback_items or []
    timely_cards = sum(len(g.members) for g in groups)
    total = timely_cards + len(fallback_items)

    if total == 0:
        return _EMPTY_MESSAGE

    # FR-008: 단일 카드 (분기 그룹 + fallback 합쳐서 1개) → 헤더 없음
    if total == 1:
        if groups:
            return _render_card_line(groups[0].members[0])
        return _render_card_line(fallback_items[0])

    out_parts: list[str] = []
    rendered = 0
    for group in groups:
        if rendered >= limit:
            break
        out_parts.append(f"## {group.quarter_label}")
        show_month_subheader = (
            len(group.members) >= 2 and len(group.months_present) >= 2
        )
        if show_month_subheader:
            # 같은 분기 안에서 월별로 다시 그룹화
            current_month: int | None = None
            for card in group.members:
                if rendered >= limit:
                    break
                if card.sort_ts.month != current_month:
                    current_month = card.sort_ts.month
                    out_parts.append(
                        f"### {card.sort_ts.year}-{current_month:02d}"
                    )
                out_parts.append(_render_card_line(card))
                rendered += 1
        else:
            for card in group.members:
                if rendered >= limit:
                    break
                out_parts.append(_render_card_line(card))
                rendered += 1

    if fallback_items and rendered < limit:
        out_parts.append(_FALLBACK_HEADER)
        # distance asc — None 은 가장 뒤로
        fallback_sorted = sorted(
            fallback_items, key=lambda c: (c.distance is None, c.distance or 0.0)
        )
        for card in fallback_sorted:
            if rendered >= limit:
                break
            out_parts.append(_render_card_line(card))
            rendered += 1

    out_parts.append(f"\n총 {rendered}개 카드 (--limit {limit})")
    return "\n\n".join(out_parts)
