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
from synapse_memory.llm.ai_api import AIEnvironment
from synapse_memory.rag import (
    VectorRecord,
    VectorStore,
    embed_query,
    hybrid_search,
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

_RESUME_RECIPE_NAME = "resume"  # 007-me-recipes — `draft_resume` 는 wrapper


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
    matched: list[tuple[VectorRecord, float]],
) -> str:
    """CompanyCard + 매칭 ProjectCard들로 AI provider prompt 빌드."""
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
    ai_env: AIEnvironment | None = None,
    store: VectorStore | None = None,
    timeout: int = DEFAULT_RESUME_TIMEOUT,
) -> ResumeDraft:
    """회사 맞춤 이력서 자동 생성 → vault에 저장 (007-me-recipes wrapper).

    내부적으로 ``recipes.pipeline.generate("resume", ...)`` 를 호출하여
    Profile + locale (CompanyCard.resume_language → Profile.preferred_lang →
    default) + domain (Profile.domain → tags → generic) 을 인식한다.

    외부 시그니처와 ``ResumeDraft`` 반환은 SC-005 회귀 가드로 보존.

    Raises:
        FileNotFoundError: CompanyCard 없음.
        AIError: 호출 실패.
        ValueError: 매칭 ProjectCard 0건.
    """
    from synapse_memory.recipes import generate as recipes_generate

    company = load_company_card(company_id, vault_path=vault_path)
    store = store or open_vector_store()

    try:
        result = recipes_generate(
            _RESUME_RECIPE_NAME,
            inputs={"company_id": company_id},
            vault_path=vault_path,
            store=store,
            ai_env=ai_env,
            model_override=model,
            timeout_override=timeout,
            company=company,
            disable_save=True,  # SC-005: wrapper 가 기존 filename rule 로 직접 저장
            top_k_override=top_k_projects,
            require_matched=True,  # ProjectCard 0 건 → ValueError
        )
    except ValueError as exc:
        # 기존 message 호환 (SC-005)
        if "got 0" in str(exc):
            raise ValueError(
                "매칭 ProjectCard 0건 — `synapse-memory rag index` 먼저 실행"
            ) from exc
        raise

    if not result.source_ids:
        raise ValueError(
            "매칭 ProjectCard 0건 — `synapse-memory rag index` 먼저 실행"
        )

    # 기존 filename rule 유지 (SC-005): `Resume - {display_name} ({YYYY-MM}).md`
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    drafts_dir = vault / DRAFTS_SUBPATH
    drafts_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    safe_name = company.display_name.replace("/", "-").replace("\\", "-")
    filename = f"Resume - {safe_name} ({today[:7]}).md"
    path = drafts_dir / filename
    path.write_text(result.answer_markdown, encoding="utf-8")

    return ResumeDraft(
        company_id=company_id,
        company_name=company.display_name,
        saved_path=path,
        project_card_ids=result.source_ids[:top_k_projects],
        raw_text=result.answer_markdown,
    )


# ---------------------------------------------------------------------------
# what_did_i_think — 주제 회상 (세컨드 브레인)
# ---------------------------------------------------------------------------


_RECALL_RECIPE_NAME = "recall"  # 007-me-recipes — what_did_i_think distance-mode wrapper


@dataclass
class WhatDidIThinkResult:
    topic: str
    answer: str
    source_ids: list[str] = field(default_factory=list)


def what_did_i_think(
    topic: str,
    *,
    top_k: int = 8,
    model: str | None = "sonnet",
    ai_env: AIEnvironment | None = None,
    store: VectorStore | None = None,
    by: Literal["time", "distance"] = "distance",
    limit: int = 20,
    today: datetime.date | None = None,
    hybrid: bool = False,
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
    if hybrid and by == "time":
        raise ValueError("--timeline and --hybrid conflict — pick one.")

    store = store or open_vector_store()
    q_vec = embed_query(topic)
    if hybrid:
        hits = hybrid_search(
            topic,
            query_embedding=q_vec,
            store=store,
            top_k=top_k,
        )
        results = [(hit.record, hit.rrf_score) for hit in hits]
    else:
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

    # distance-mode → recipes.generate("recall", ...) wrapper (007 R-7)
    from synapse_memory.recipes import generate as recipes_generate

    # 006 hybrid 결과 또는 기존 dense 결과를 007 recipe pipeline 의 matched-record
    # 인터페이스로 그대로 전달한다. store 를 재사용하면 hybrid order 가 dense query 로
    # 덮일 수 있다.
    result = recipes_generate(
        _RECALL_RECIPE_NAME,
        inputs={"topic": topic},
        store=_PrecomputedResultStore(results),
        ai_env=ai_env,
        model_override=model,
        top_k_override=top_k,
        disable_save=True,
    )
    return WhatDidIThinkResult(
        topic=topic,
        answer=result.answer_markdown,
        source_ids=result.source_ids,
    )


class _PrecomputedResultStore:
    def __init__(self, results: list[tuple[VectorRecord, float]]) -> None:
        self._results = results

    def query(self, *_args: object, **_kwargs: object) -> list[tuple[VectorRecord, float]]:
        return list(self._results)


# ---------------------------------------------------------------------------
# decide — 의사결정 코파일럿
# ---------------------------------------------------------------------------


_DECIDE_RECIPE_NAME = "decide"  # 007-me-recipes — decide() wrapper


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
    ai_env: AIEnvironment | None = None,
    store: VectorStore | None = None,
    vault_path: Path | None = None,
) -> DecideResult:
    """의사결정 코파일럿 (007-me-recipes wrapper).

    내부적으로 ``recipes.pipeline.generate("decide", ...)`` 를 호출한다.
    외부 시그니처와 ``DecideResult`` 반환은 SC-005 회귀 가드로 보존.
    """
    if not situation.strip():
        raise ValueError("situation은 빈 문자열일 수 없음")

    from synapse_memory.recipes import generate as recipes_generate

    store = store or open_vector_store()

    result = recipes_generate(
        _DECIDE_RECIPE_NAME,
        inputs={"situation": situation},
        vault_path=vault_path,
        store=store,
        ai_env=ai_env,
        model_override=model,
        top_k_override=top_k,
        disable_save=True,
    )
    return DecideResult(
        situation=situation,
        answer=result.answer_markdown,
        profile_used=result.profile_used,
        source_ids=result.source_ids,
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
        command=command,
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
