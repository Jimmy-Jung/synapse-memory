"""RAG layer — provider-only (020).

로컬 ML(embeddings/vector_store/bm25/hybrid/indexer)은 완전히 제거되었다. 검색·선별은
``wiki.llm_retrieval.select_related`` + ``cards.card_index.build_card_index`` provider
경로로 일원화되었다. 남은 것은 raw 텍스트 청킹 유틸(``chunker``) 뿐이다.

저자: Synapse Memory Maintainers
"""

from synapse_memory.rag.chunker import (
    RawChunk,
    RawSource,
    chunk_text,
    discover_raw_sources,
    raw_chunks_from_file,
    tokenize_text,
)

__all__ = [
    "RawChunk",
    "RawSource",
    "chunk_text",
    "discover_raw_sources",
    "raw_chunks_from_file",
    "tokenize_text",
]
