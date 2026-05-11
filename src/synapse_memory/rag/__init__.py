"""RAG (Retrieval-Augmented Generation) layer.

- embeddings: 로컬 임베딩 모델 (bge-m3, 한국어/영어 강함)
- vector_store: ChromaDB persistent collection
- retrieval (W4 후반): hybrid search (dense + BM25 + RRF)
- indexer (W4 후반): Card → 임베딩 → DB

핵심 보안 원칙: raw 텍스트는 임베드 안 함. **redacted 또는 검증된 Card만 인덱싱.**

저자: JunyoungJung <joony300@gmail.com>
"""

from synapse_memory.rag.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingError,
    EmbeddingUnavailableError,
    embed_query,
    embed_texts,
    get_embedder,
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
    "EmbeddingError",
    "EmbeddingUnavailableError",
    "IndexStats",
    "VectorRecord",
    "VectorStore",
    "company_card_to_text",
    "embed_query",
    "embed_texts",
    "get_embedder",
    "index_cards",
    "open_vector_store",
    "project_card_to_text",
]
