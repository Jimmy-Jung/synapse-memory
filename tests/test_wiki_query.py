"""wiki-first ask + 인용 + insight write-back (_retrieve_wiki/LLM 주입)."""
from __future__ import annotations

import datetime
from pathlib import Path  # noqa: F401

import synapse_memory.wiki.query as q
from synapse_memory.model import Entity
from synapse_memory.wiki.page import load_page, save_page


def test_ask_wiki_synthesizes_with_citation(tmp_path, monkeypatch) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG", body="검색 증강 생성"), vault_path=tmp_path)
    monkeypatch.setattr(q, "_retrieve_wiki",
        lambda query, *, vault_path, top_k: [load_page("concept", "rag", vault_path=vault_path)])
    monkeypatch.setattr(q.ai_api, "complete", lambda *a, **k: "RAG는 검색 증강 생성입니다 [[rag]]")
    res = q.ask_wiki("RAG가 뭐야?", vault_path=tmp_path)
    assert "RAG" in res.answer
    assert "rag" in res.sources


def test_ask_wiki_writeback_creates_insight(tmp_path, monkeypatch) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG", body="x"), vault_path=tmp_path)
    monkeypatch.setattr(q, "_retrieve_wiki",
        lambda query, *, vault_path, top_k: [load_page("concept", "rag", vault_path=vault_path)])
    monkeypatch.setattr(q.ai_api, "complete", lambda *a, **k: "답변 본문 [[rag]]")
    res = q.ask_wiki("RAG 설명", vault_path=tmp_path, save=True, today="2026-06-14")
    assert res.saved_slug is not None
    insight = load_page("insight", res.saved_slug, vault_path=tmp_path, when=datetime.date(2026, 6, 14))
    assert "답변 본문" in insight.body


def test_ask_wiki_no_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(q, "_retrieve_wiki", lambda query, *, vault_path, top_k: [])
    res = q.ask_wiki("아무거나", vault_path=tmp_path)
    assert res.sources == []
    assert "없" in res.answer  # "자료에 없음"
