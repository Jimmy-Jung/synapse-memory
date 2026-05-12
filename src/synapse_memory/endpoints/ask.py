"""ask endpoint — RAG retrieve + Claude 합성.

흐름::

    query → embed_query → vector_store.query(top_k) → 컨텍스트 구성 →
    Claude (system: ASK_SYSTEM) → 자연어 답변 + 출처 인용

원칙
----
- **자료에 없는 정보는 추측 안 함** (system prompt + post-check)
- 각 주장에 출처 인용 ``[card_id]``
- 사용자 vault Card만 근거 — 외부 지식 사용 금지

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

from synapse_memory.llm import claude as claude_api
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.rag import (
    VectorStore,
    embed_query,
    open_vector_store,
)
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


def _build_context(results: list[tuple]) -> str:
    """retrieved records → Claude 입력용 컨텍스트 문자열."""
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
    model: str = DEFAULT_MODEL,
    store: VectorStore | None = None,
    claude_env: ClaudeEnvironment | None = None,
    where: dict | None = None,
) -> AskResult:
    """질의 → RAG → Claude 답변.

    Args:
        query: 사용자 자연어 질의.
        top_k: retrieve할 Card 수.
        model: Claude 모델 (sonnet 권장).
        store: vector store (기본 자동).
        claude_env: 사전 진단 (재사용 시).
        where: metadata filter (예: ``{"source_kind": "card_project"}``).

    Returns:
        AskResult — answer + sources.

    Raises:
        ClaudeError / VectorStoreError / EmbeddingError: 단계별 실패.
    """
    if not query.strip():
        raise ValueError("query는 빈 문자열일 수 없음")

    store = store or open_vector_store()
    q_vec = embed_query(query)
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

    answer = claude_api.complete(
        user_prompt,
        system=ASK_SYSTEM,
        model=model,
        env=claude_env,
        timeout=120,
    )

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
    return AskResult(query=query, answer=answer, sources=sources)


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
