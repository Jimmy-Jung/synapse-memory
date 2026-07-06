"""ask endpoint — provider 선별 retrieve + AI provider 합성 (020).

흐름::

    query → build_card_index → select_related(provider) → 선택 카드 full text →
    AI provider (system: ASK_SYSTEM) → 자연어 답변 + 출처 인용

원칙
----
- **자료에 없는 정보는 추측 안 함** (system prompt + post-check)
- 각 주장에 출처 인용 ``[card_id]``
- 사용자 vault Card만 근거 — 외부 지식 사용 금지

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from synapse_memory.cards.card_index import CardKind, build_card_index
from synapse_memory.cards.insight import (
    InsightCard,
    new_insight_id,
    save_insight_card,
)
from synapse_memory.endpoints.postprocess import strip_meta_prefix
from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import AIEnvironment
from synapse_memory.retrieval.index import select_related
from synapse_memory.storage.last_response import (
    AnswerCitation,
    new_answer_reference,
    save_last_answer,
)

ASK_SYSTEM = """당신은 사용자의 개인 세컨드 브레인입니다.

# 원칙
- 아래 제공된 Card 자료**만** 근거로 답변합니다.
- 자료에 없는 정보는 **추측하지 않습니다** — "자료에 없음"이라고 솔직히 답합니다.
- 각 주장 끝에 출처를 ``[card_id]`` 형식으로 인용합니다.
- 한국어로 자연스럽게, 사용자에게 직접 말하듯 답변합니다.
- 짧고 정확하게. 불필요한 인사·반복 금지.

# 출력
첫 줄에 핵심 답변. 그 다음 필요 시 상세."""

DEFAULT_TOP_K = 5
DEFAULT_MODEL = "sonnet"
SOURCE_DOC_CHARS = 2000  # 한 source당 컨텍스트로 보낼 문자 수


@dataclass
class SourceCitation:
    card_id: str
    source_kind: str
    display_name: str
    distance: float = 0.0  # provider 선별이라 거리 없음 — 호환 위해 0.0 유지


@dataclass
class AskResult:
    query: str
    answer: str
    sources: list[SourceCitation] = field(default_factory=list)
    saved_path: Path | None = None


# where=kind 필터 → CardIndex kind 매핑
_SOURCE_KIND_TO_CARD_KIND: dict[str, CardKind] = {
    "card_project": "project",
    "card_company": "company",
    "card_insight": "insight",
}


def _kinds_from_where(where: dict[str, object] | None) -> tuple[CardKind, ...]:
    """``where={"source_kind": "card_project"}`` → CardIndex kinds. 미지정이면 전체."""
    if where:
        source_kind = where.get("source_kind")
        if isinstance(source_kind, str) and source_kind in _SOURCE_KIND_TO_CARD_KIND:
            return (_SOURCE_KIND_TO_CARD_KIND[source_kind],)
    return ("project", "company", "insight")


def _load_card_text(
    card_id: str,
    kind: CardKind,
    vault_path: Path | None,
    *,
    created: str = "",
) -> str:
    """선별된 card_id의 full text 로드. 실패 시 빈 문자열."""
    from synapse_memory.cards.card_text import (
        company_card_to_text,
        insight_card_to_text,
        project_card_to_text,
    )
    from synapse_memory.cards.company import load_company_card
    from synapse_memory.cards.insight import load_insight_card
    from synapse_memory.cards.project import load_project_card

    try:
        if kind == "project":
            return project_card_to_text(load_project_card(card_id, vault_path=vault_path))
        if kind == "company":
            return company_card_to_text(load_company_card(card_id, vault_path=vault_path))
        if not created:
            return ""
        return insight_card_to_text(
            load_insight_card(card_id, created, vault_path=vault_path)
        )
    except (FileNotFoundError, ValueError, OSError):
        return ""


def ask(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    model: str | None = DEFAULT_MODEL,
    store: object | None = None,  # 시그니처 호환 — provider 선별로 미사용
    ai_env: AIEnvironment | None = None,
    where: dict[str, object] | None = None,
    hybrid: bool = False,  # 폐기 — provider 선별로 일원화 (시그니처 호환)
    save: bool = False,
    vault_path: Path | None = None,
) -> AskResult:
    """질의 → provider 선별 retrieve → AI provider 답변 (020).

    Args:
        query: 사용자 자연어 질의.
        top_k: 선별할 Card 수 상한.
        model: AI 모델 (sonnet 권장).
        ai_env: 사전 진단 (재사용 시).
        where: card kind 필터 (예: ``{"source_kind": "card_project"}``).

    Returns:
        AskResult — answer + sources.

    Raises:
        AIError: 합성 단계 실패.
    """
    if not query.strip():
        raise ValueError("query는 빈 문자열일 수 없음")

    kinds = _kinds_from_where(where)
    index = build_card_index(vault_path=vault_path, kinds=kinds)
    selected = select_related(query, index, max_pages=top_k) if index.entries else []

    if not selected:
        return AskResult(
            query=query,
            answer="자료 없음 — vault에 관련 Card를 먼저 생성하세요 (`synapse-memory daily`).",
            sources=[],
        )

    by_id = index.by_id()
    context_parts: list[str] = []
    sources: list[SourceCitation] = []
    for card_id in selected:
        entry = by_id.get(card_id)
        if entry is None:
            continue
        text = _load_card_text(
            card_id,
            entry.kind,
            vault_path,
            created=entry.meta.get("created", ""),
        )
        snippet = (text or entry.summary)[:SOURCE_DOC_CHARS]
        kind_meta = entry.meta.get("source_kind", "unknown")
        name = entry.meta.get("display_name", entry.title)
        context_parts.append(f"---\n[{card_id}] ({kind_meta}, {name})\n{snippet}\n")
        sources.append(
            SourceCitation(
                card_id=card_id,
                source_kind=kind_meta,
                display_name=name,
            )
        )

    context = "\n".join(context_parts)
    user_prompt = (
        f"# 질문\n{query}\n\n"
        f"# 자료\n{context}\n\n"
        f"위 자료를 근거로 답변하세요. 추측 금지."
    )

    answer = ai_api.complete(
        user_prompt,
        system=ASK_SYSTEM,
        model=model,
        env=ai_env,
        timeout=120,
    )
    answer = strip_meta_prefix(answer)

    _record_last_answer(query, sources)
    result = AskResult(query=query, answer=answer, sources=sources)
    if save:
        result.saved_path = save_insight_from_ask(result)
    return result


def save_insight_from_ask(result: AskResult) -> Path:
    """AskResult를 InsightCard로 저장한다 (벡터 인덱싱 제거 — 020)."""
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    related = list(dict.fromkeys(source.card_id for source in result.sources))
    card = InsightCard(
        insight_id=new_insight_id(result.query),
        question=result.query,
        command="ask",
        created=created,
        related=related,
        body=result.answer,
    )
    return save_insight_card(card)


def _record_last_answer(query: str, sources: list[SourceCitation]) -> None:
    citations = tuple(
        AnswerCitation(
            target_kind="card",
            target_ref=s.card_id,
            source_kind=s.source_kind,
            display_name=s.display_name,
        )
        for s in sources
    )
    ref = new_answer_reference(command="ask", query=query, citations=citations)
    with contextlib.suppress(OSError, ValueError):
        save_last_answer(ref)
