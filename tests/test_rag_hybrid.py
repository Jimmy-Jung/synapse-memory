"""Hybrid retrieval ranking tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synapse_memory.rag.bm25 import BM25Document, BM25IndexError, write_bm25_documents
from synapse_memory.rag.hybrid import (
    hybrid_search,
    reciprocal_rank_fusion,
    reciprocal_rank_score,
)
from synapse_memory.rag.vector_store import VectorRecord


def _record(record_id: str, text: str) -> VectorRecord:
    return VectorRecord(
        id=record_id,
        document=text,
        embedding=[0.0],
        metadata={"source_kind": "card_project", "card_id": record_id.rsplit(":", 1)[-1]},
    )


def _bm25_doc(record_id: str, text: str) -> BM25Document:
    return BM25Document(
        record_id=record_id,
        text=text,
        tokens=text.split(),
        metadata={"source_kind": "card_project", "card_id": record_id.rsplit(":", 1)[-1]},
    )


def test_reciprocal_rank_score() -> None:
    assert reciprocal_rank_score(1, k=60) == 1 / 61


def test_reciprocal_rank_fusion_promotes_bm25_exact_match() -> None:
    dense = [
        (_record("card_project:semantic", "의미상 가까운 문서"), 0.1),
        (_record("card_company:danggeun", "당근마켓 중고거래"), 0.4),
    ]
    bm25 = [
        (_bm25_doc("card_company:danggeun", "당근마켓 중고거래"), 3.0),
        (_bm25_doc("card_project:semantic", "의미상 가까운 문서"), 0.1),
    ]

    hits = reciprocal_rank_fusion(dense, bm25, top_k=2, k=60)

    assert hits[0].record.id == "card_company:danggeun"
    assert hits[0].dense_rank == 2
    assert hits[0].bm25_rank == 1
    assert hits[0].rrf_score == hits[1].rrf_score
    assert hits[0].bm25_score is not None
    assert hits[1].bm25_score is not None
    assert hits[0].bm25_score > hits[1].bm25_score


def test_reciprocal_rank_fusion_includes_bm25_only_record() -> None:
    hits = reciprocal_rank_fusion(
        dense=[(_record("card_project:semantic", "semantic"), 0.2)],
        bm25=[(_bm25_doc("raw_obsidian:abc:0", "당근마켓 raw"), 2.0)],
        top_k=2,
    )

    assert {hit.record.id for hit in hits} == {
        "card_project:semantic",
        "raw_obsidian:abc:0",
    }
    raw_hit = next(hit for hit in hits if hit.record.id == "raw_obsidian:abc:0")
    assert raw_hit.record.document == "당근마켓 raw"
    assert raw_hit.dense_rank is None
    assert raw_hit.bm25_rank == 1


def test_hybrid_search_combines_store_and_bm25_sidecar(tmp_path: Path) -> None:
    store = MagicMock()
    store.query.return_value = [
        (_record("card_project:semantic", "의미상 가까운 문서"), 0.1),
        (_record("card_company:danggeun", "당근마켓 중고거래"), 0.4),
    ]
    sidecar = tmp_path / "bm25.jsonl"
    write_bm25_documents(
        [
            _bm25_doc("card_project:semantic", "의미상 가까운 문서"),
            _bm25_doc("card_company:danggeun", "당근마켓 중고거래"),
        ],
        path=sidecar,
    )

    hits = hybrid_search(
        "당근마켓 경험",
        query_embedding=[0.0],
        store=store,
        top_k=2,
        bm25_path=sidecar,
    )

    assert hits[0].record.id == "card_company:danggeun"
    assert store.query.call_args.kwargs["top_k"] == 4


def test_hybrid_search_missing_sidecar_raises(tmp_path: Path) -> None:
    store = MagicMock()
    store.query.return_value = []

    with pytest.raises(BM25IndexError):
        hybrid_search(
            "당근마켓",
            query_embedding=[0.0],
            store=store,
            bm25_path=tmp_path / "missing.jsonl",
        )


def test_synthetic_proper_noun_fixture_hybrid_improves_top1() -> None:
    fixture = Path("tests/golden/raw_rag_hybrid/synthetic_queries.json")
    rows = json.loads(fixture.read_text(encoding="utf-8"))

    improvements = [
        row for row in rows if row["dense_rank"] > 1 and row["bm25_rank"] == 1
    ]

    assert len(rows) >= 2
    assert len(improvements) == len(rows)
