"""BM25 sidecar tests.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.rag.bm25 import (
    BM25Document,
    BM25IndexError,
    load_bm25_documents,
    search_bm25,
    tokenize_for_bm25,
    write_bm25_documents,
)


def test_tokenize_for_bm25_handles_korean_and_slug() -> None:
    assert tokenize_for_bm25("당근마켓 dansim-ios TCA") == [
        "당근마켓",
        "dansim",
        "ios",
        "tca",
    ]


def test_write_and_load_bm25_documents(tmp_path: Path) -> None:
    path = tmp_path / "bm25.jsonl"
    docs = [
        BM25Document(
            record_id="card_company:danggeun",
            text="당근마켓 중고거래",
            tokens=["당근마켓", "중고거래"],
            metadata={"source_kind": "card_company", "card_id": "danggeun"},
        )
    ]

    write_bm25_documents(docs, path=path)

    assert load_bm25_documents(path=path) == docs


def test_search_bm25_prioritizes_exact_keyword() -> None:
    docs = [
        BM25Document(
            record_id="card_project:other",
            text="모바일 플랫폼",
            tokens=tokenize_for_bm25("모바일 플랫폼"),
            metadata={"source_kind": "card_project", "card_id": "other"},
        ),
        BM25Document(
            record_id="card_company:danggeun",
            text="당근마켓 중고거래",
            tokens=tokenize_for_bm25("당근마켓 중고거래"),
            metadata={"source_kind": "card_company", "card_id": "danggeun"},
        ),
    ]

    results = search_bm25("당근마켓 경험", docs, top_k=2)

    assert results[0][0].record_id == "card_company:danggeun"
    assert results[0][1] > 0


def test_load_missing_sidecar_raises(tmp_path: Path) -> None:
    with pytest.raises(BM25IndexError):
        load_bm25_documents(path=tmp_path / "missing.jsonl", require=True)


def test_write_bm25_documents_rejects_prohibited_raw_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_bm25_documents(
            [
                BM25Document(
                    record_id="raw_obsidian:abc:0",
                    text="redacted",
                    tokens=["redacted"],
                    metadata={"source_kind": "raw_obsidian", "raw_prompt": "secret"},
                )
            ],
            path=tmp_path / "bm25.jsonl",
        )
