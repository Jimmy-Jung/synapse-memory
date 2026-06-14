"""ask endpoint — RAG retrieve + AI provider 합성.

흐름::

    query → embed_query → vector_store.query(top_k) → 컨텍스트 구성 →
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

from synapse_memory.cards.insight import (
    InsightCard,
    new_insight_id,
    save_insight_card,
)
from synapse_memory.endpoints.postprocess import strip_meta_prefix
from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import AIEnvironment
from synapse_memory.rag import (
    VectorRecord,
    VectorStore,
    embed_query,
    hybrid_search,
    open_vector_store,
)
from synapse_memory.rag.indexer import index_insight_card
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
    distance: float


@dataclass
class AskResult:
    query: str
    answer: str
    sources: list[SourceCitation] = field(default_factory=list)
    saved_path: Path | None = None


def _build_context(results: list[tuple[VectorRecord, float]]) -> str:
    """retrieved records → AI provider 입력용 컨텍스트 문자열."""
    parts: list[str] = []
    for rec, dist in results:
        meta = rec.metadata or {}
        kind = meta.get("source_kind", "unknown")
        cid = meta.get("card_id") or rec.id
        name = meta.get("display_name", cid)
        snippet = rec.document[:SOURCE_DOC_CHARS]
        parts.append(
            f"---\n"
            f"[{cid}] ({kind}, {name}, 유사도 거리={dist:.3f})\n"
            f"{snippet}\n"
        )
    return "\n".join(parts)


def ask(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    model: str | None = DEFAULT_MODEL,
    store: VectorStore | None = None,
    ai_env: AIEnvironment | None = None,
    where: dict[str, object] | None = None,
    hybrid: bool = False,
    save: bool = False,
) -> AskResult:
    """질의 → RAG → AI provider 답변.

    Args:
        query: 사용자 자연어 질의.
        top_k: retrieve할 Card 수.
        model: AI 모델 (sonnet 권장).
        store: vector store (기본 자동).
        ai_env: 사전 진단 (재사용 시).
        where: metadata filter (예: ``{"source_kind": "card_project"}``).

    Returns:
        AskResult — answer + sources.

    Raises:
        AIError / VectorStoreError / EmbeddingError: 단계별 실패.
    """
    if not query.strip():
        raise ValueError("query는 빈 문자열일 수 없음")

    store = store or open_vector_store()
    q_vec = embed_query(query)
    if hybrid:
        hits = hybrid_search(
            query,
            query_embedding=q_vec,
            store=store,
            top_k=top_k,
            where=where,
        )
        results = [(hit.record, hit.rrf_score) for hit in hits]
    else:
        results = store.query(q_vec, top_k=top_k, where=where)

    if not results:
        return AskResult(
            query=query,
            answer="자료 없음 — `synapse-memory rag index` 먼저 실행하세요.",
            sources=[],
        )

    context = _build_context(results)

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

    sources = [
        SourceCitation(
            card_id=rec.metadata.get("card_id") or rec.id,
            source_kind=rec.metadata.get("source_kind", "unknown"),
            display_name=rec.metadata.get("display_name", ""),
            distance=dist,
        )
        for rec, dist in results
    ]
    _record_last_answer(query, sources)
    result = AskResult(query=query, answer=answer, sources=sources)
    if save:
        result.saved_path = save_insight_from_ask(result)
    return result


def save_insight_from_ask(result: AskResult) -> Path:
    """AskResult를 InsightCard로 저장하고 best-effort로 인덱싱한다."""
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
    path = save_insight_card(card)
    with contextlib.suppress(Exception):
        index_insight_card(card)
    return path


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
