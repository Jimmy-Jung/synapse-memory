"""RAG (Retrieval-Augmented Generation) layer.

- embeddings: 로컬 임베딩 모델 (bge-m3, 한국어/영어 강함)
- vector_store: ChromaDB persistent collection
- retrieval (W4 후반): hybrid search (dense + BM25 + RRF)
- indexer (W4 후반): Card → 임베딩 → DB

핵심 보안 원칙: raw 텍스트는 임베드 안 함. **redacted 또는 검증된 Card만 인덱싱.**

저자: JunyoungJung <joony300@gmail.com>
"""

from synapse_memory.rag.bm25 import (
    BM25Document,
    BM25IndexError,
    load_bm25_documents,
    search_bm25,
    tokenize_for_bm25,
    write_bm25_documents,
)
from synapse_memory.rag.chunker import (
    RawChunk,
    RawSource,
    chunk_text,
    discover_raw_sources,
    raw_chunks_from_file,
    tokenize_text,
)
from synapse_memory.rag.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingError,
    EmbeddingUnavailableError,
    embed_query,
    embed_texts,
    get_embedder,
)
from synapse_memory.rag.hybrid import (
    DEFAULT_RRF_K,
    RetrievalHit,
    hybrid_search,
    reciprocal_rank_fusion,
    reciprocal_rank_score,
)
from synapse_memory.rag.indexer import (
    IndexStats,
    company_card_to_text,
    index_cards,
    project_card_to_text,
)
from synapse_memory.rag.vector_store import (
    DEFAULT_COLLECTION,
    VectorRecord,
    VectorStore,
    open_vector_store,
)

__all__ = [
    "DEFAULT_COLLECTION",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_RRF_K",
    "BM25Document",
    "BM25IndexError",
    "EmbeddingError",
    "EmbeddingUnavailableError",
    "IndexStats",
    "RawChunk",
    "RawSource",
    "RetrievalHit",
    "VectorRecord",
    "VectorStore",
    "chunk_text",
    "company_card_to_text",
    "discover_raw_sources",
    "embed_query",
    "embed_texts",
    "get_embedder",
    "hybrid_search",
    "index_cards",
    "load_bm25_documents",
    "open_vector_store",
    "project_card_to_text",
    "raw_chunks_from_file",
    "reciprocal_rank_fusion",
    "reciprocal_rank_score",
    "search_bm25",
    "tokenize_for_bm25",
    "tokenize_text",
    "write_bm25_documents",
]
