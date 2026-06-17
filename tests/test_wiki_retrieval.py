# tests/test_wiki_retrieval.py
"""find_related_pages: 이름매칭 + 1-hop 링크 확장.

020: 기본 semantic은 provider LLM 호출이므로, 이름매칭/1-hop만 검증하는 이 테스트는
``semantic_fn=None``으로 의미선별을 꺼서 hermetic하게 유지한다.
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.page import WikiPage, save_page
from synapse_memory.wiki.retrieval import find_related_pages


def test_name_match_by_title_and_slug(tmp_path: Path) -> None:
    save_page(WikiPage(type="project", slug="synapse-memory", title="Synapse Memory"), vault_path=tmp_path)
    save_page(WikiPage(type="company", slug="acme", title="Acme Corp"), vault_path=tmp_path)
    hits = find_related_pages("오늘 Synapse Memory 작업했다", vault_path=tmp_path, max_pages=10, semantic_fn=None)
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "acme" not in slugs


def test_one_hop_link_expansion(tmp_path: Path) -> None:
    save_page(WikiPage(type="project", slug="synapse-memory", title="Synapse Memory",
                       related=("[[rag]]",)), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    hits = find_related_pages("Synapse Memory 진행", vault_path=tmp_path, max_pages=10, semantic_fn=None)
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "rag" in slugs


def test_respects_max_pages(tmp_path: Path) -> None:
    for i in range(5):
        save_page(WikiPage(type="concept", slug=f"c{i}", title=f"Concept{i}"), vault_path=tmp_path)
    text = " ".join(f"Concept{i}" for i in range(5))
    hits = find_related_pages(text, vault_path=tmp_path, max_pages=2, semantic_fn=None)
    assert len(hits) == 2


def test_no_match_returns_empty(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    assert find_related_pages("관련 없는 내용", vault_path=tmp_path, semantic_fn=None) == []
