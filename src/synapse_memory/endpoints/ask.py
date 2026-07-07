"""ask endpoint — builtin recipe adapter.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from synapse_memory.cards.insight import (
    InsightCard,
    new_insight_id,
    save_insight_card,
)
from synapse_memory.feedback.last_response import (
    AnswerCitation,
    LastAnswerReference,
    new_answer_reference,
    save_last_answer,
)
from synapse_memory.llm.ai_api import AIEnvironment
from synapse_memory.recipes import generate as recipes_generate
from synapse_memory.recipes.kinds import is_known_source_kind

_ASK_RECIPE_NAME = "ask"
DEFAULT_TOP_K = 5
DEFAULT_MODEL = "sonnet"


@dataclass
class SourceCitation:
    card_id: str
    source_kind: str
    display_name: str
    distance: float = 0.0


@dataclass
class AskResult:
    query: str
    answer: str
    sources: list[SourceCitation] = field(default_factory=list)
    saved_path: Path | None = None


def _rag_filter_from_where(where: dict[str, object] | None) -> dict[str, str] | None:
    if not where:
        return None
    source_kind = where.get("source_kind")
    if is_known_source_kind(source_kind):
        return {"source_kind": str(source_kind)}
    return None


def _sources_from_last_ref(ref: LastAnswerReference | None) -> list[SourceCitation]:
    if ref is None:
        return []
    return [
        SourceCitation(
            card_id=c.target_ref,
            source_kind=c.source_kind,
            display_name=c.display_name,
        )
        for c in ref.citations
    ]


def ask(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    model: str | None = DEFAULT_MODEL,
    store: object | None = None,
    ai_env: AIEnvironment | None = None,
    where: dict[str, object] | None = None,
    hybrid: bool = False,
    save: bool = False,
    vault_path: Path | None = None,
) -> AskResult:
    """질의 → builtin ``ask`` recipe → endpoint 호환 result."""
    if not query.strip():
        raise ValueError("query는 빈 문자열일 수 없음")

    result = recipes_generate(
        _ASK_RECIPE_NAME,
        inputs={"query": query},
        vault_path=vault_path,
        store=store,
        ai_env=ai_env,
        model_override=model,
        top_k_override=top_k,
        disable_save=True,
        save_last=False,
        return_empty_on_no_matches=True,
        rag_filter_override=_rag_filter_from_where(where),
    )
    sources = _sources_from_last_ref(result.last_answer_ref)
    if not sources:
        return AskResult(
            query=query,
            answer="자료 없음 — vault에 관련 Entity를 먼저 생성하세요 (`synapse-memory daily`).",
            sources=[],
        )

    _record_last_answer(query, sources)
    ask_result = AskResult(query=query, answer=result.answer_markdown, sources=sources)
    if save:
        ask_result.saved_path = save_insight_from_ask(ask_result)
    return ask_result


def save_insight_from_ask(result: AskResult) -> Path:
    """AskResult를 InsightCard로 저장한다."""
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
