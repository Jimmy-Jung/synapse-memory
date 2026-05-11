"""me endpoints — 사용자 voice/data로 결과 생성하는 클론 모드.

- draft_resume      : 회사 맞춤 이력서
- what_did_i_think  : 주제 회상 (세컨드 브레인, 시간순)
- decide            : 의사결정 코파일럿 (Profile + DecisionPatterns + RAG)

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.cards.company import CompanyCard, load_company_card
from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.llm import claude as claude_api
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.rag import (
    VectorStore,
    embed_query,
    open_vector_store,
)
from synapse_memory.rag.indexer import company_card_to_text

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
) -> WhatDidIThinkResult:
    """주제에 대한 과거 사고 회상."""
    if not topic.strip():
        raise ValueError("topic은 빈 문자열일 수 없음")

    store = store or open_vector_store()
    q_vec = embed_query(topic)
    results = store.query(q_vec, top_k=top_k)

    if not results:
        return WhatDidIThinkResult(
            topic=topic,
            answer="자료 없음 — `synapse-memory rag index` 먼저",
            source_ids=[],
        )

    parts: list[str] = []
    source_ids: list[str] = []
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
    return DecideResult(
        situation=situation,
        answer=answer,
        profile_used=profile_used,
        source_ids=source_ids,
    )
