"""Hybrid dense/BM25 retrieval helpers.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse_memory.rag.bm25 import (
    BM25Document,
    BM25IndexError,
    load_bm25_documents,
    search_bm25,
)
from synapse_memory.rag.vector_store import VectorRecord, VectorStore

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class RetrievalHit:
    record: VectorRecord
    dense_rank: int | None
    dense_distance: float | None
    bm25_rank: int | None
    bm25_score: float | None
    rrf_score: float


def reciprocal_rank_score(rank: int, *, k: int = DEFAULT_RRF_K) -> float:
    if rank < 1:
        raise ValueError("rank must be >= 1")
    return 1 / (k + rank)


def reciprocal_rank_fusion(
    dense: list[tuple[VectorRecord, float]],
    bm25: list[tuple[BM25Document, float]],
    *,
    top_k: int = 10,
    k: int = DEFAULT_RRF_K,
) -> list[RetrievalHit]:
    """Dense and BM25 ranked lists를 RRF로 결합한다."""
    by_id: dict[str, _HitBuilder] = {}

    for rank, (record, distance) in enumerate(dense, start=1):
        builder = by_id.setdefault(record.id, _HitBuilder(record=record))
        builder.dense_rank = rank
        builder.dense_distance = distance
        builder.rrf_score += reciprocal_rank_score(rank, k=k)

    for rank, (doc, score) in enumerate(bm25, start=1):
        builder = by_id.setdefault(doc.record_id, _HitBuilder(record=_record_from_bm25(doc)))
        builder.bm25_rank = rank
        builder.bm25_score = score
        builder.rrf_score += reciprocal_rank_score(rank, k=k)

    hits = [builder.build() for builder in by_id.values()]
    hits.sort(
        key=lambda hit: (
            -hit.rrf_score,
            -(hit.bm25_score if hit.bm25_score is not None else float("-inf")),
            hit.dense_distance if hit.dense_distance is not None else float("inf"),
            hit.record.id,
        )
    )
    return hits[:top_k]


def hybrid_search(
    query: str,
    *,
    query_embedding: list[float],
    store: VectorStore,
    top_k: int = 10,
    where: dict[str, object] | None = None,
    bm25_path: Path | None = None,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[RetrievalHit]:
    """VectorStore dense 결과와 BM25 sidecar 결과를 RRF로 결합한다."""
    dense_top_k = max(top_k * 2, top_k)
    dense_results = store.query(query_embedding, top_k=dense_top_k, where=where)

    documents = load_bm25_documents(path=bm25_path, require=True)
    documents = [
        doc for doc in documents if _metadata_matches_where(doc.metadata, where)
    ]
    if not documents:
        raise BM25IndexError("BM25 sidecar에 검색 가능한 문서가 없습니다")

    bm25_results = search_bm25(query, documents, top_k=dense_top_k)
    return reciprocal_rank_fusion(
        dense_results,
        bm25_results,
        top_k=top_k,
        k=rrf_k,
    )


@dataclass
class _HitBuilder:
    record: VectorRecord
    dense_rank: int | None = None
    dense_distance: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rrf_score: float = 0.0

    def build(self) -> RetrievalHit:
        return RetrievalHit(
            record=self.record,
            dense_rank=self.dense_rank,
            dense_distance=self.dense_distance,
            bm25_rank=self.bm25_rank,
            bm25_score=self.bm25_score,
            rrf_score=self.rrf_score,
        )


def _record_from_bm25(doc: BM25Document) -> VectorRecord:
    return VectorRecord(
        id=doc.record_id,
        document=doc.text,
        embedding=[],
        metadata=dict(doc.metadata),
    )


def _metadata_matches_where(
    metadata: dict[str, Any],
    where: dict[str, object] | None,
) -> bool:
    if not where:
        return True
    return all(metadata.get(key) == value for key, value in where.items())
