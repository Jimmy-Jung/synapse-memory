"""wiki 페이지 → 벡터 레코드 + 인덱싱 (store/embed 주입)."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.index import (
    WIKI_SOURCE_KIND,
    index_wiki_pages,
    wiki_page_to_record,
    wiki_page_to_text,
)
from synapse_memory.wiki.page import WikiPage, save_page


class FakeStore:
    def __init__(self): self.records = []
    def upsert(self, records): self.records.extend(records); return len(records)


def _embed(texts): return [[float(len(t))] for t in texts]


def test_page_to_text_includes_title_and_body() -> None:
    page = WikiPage(type="concept", slug="rag", title="RAG", body="검색 증강")
    text = wiki_page_to_text(page)
    assert "RAG" in text and "검색 증강" in text


def test_page_to_record_id_and_metadata() -> None:
    page = WikiPage(type="project", slug="synapse-memory", title="Synapse Memory", body="b")
    rec = wiki_page_to_record(page, embedding=[1.0])
    assert rec.id == "wiki:project:synapse-memory"
    assert rec.metadata["source_kind"] == WIKI_SOURCE_KIND
    assert rec.metadata["type"] == "project"
    assert rec.metadata["slug"] == "synapse-memory"
    assert rec.metadata["title"] == "Synapse Memory"


def test_index_wiki_pages_upserts_all(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG", body="a"), vault_path=tmp_path)
    save_page(WikiPage(type="project", slug="sm", title="SM", body="b"), vault_path=tmp_path)
    store = FakeStore()
    n = index_wiki_pages(vault_path=tmp_path, store=store, embed_fn=_embed)
    assert n == 2
    assert {r.id for r in store.records} == {"wiki:concept:rag", "wiki:project:sm"}
