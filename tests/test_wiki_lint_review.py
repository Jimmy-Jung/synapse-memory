from __future__ import annotations
from synapse_memory.wiki.lint import merge_candidates, stale_candidates
from synapse_memory.wiki.page import WikiPage


def _p(slug, title, updated=""):
    return WikiPage(type="concept", slug=slug, title=title, updated=updated)


def test_stale_by_age() -> None:
    pages = [_p("old", "Old", "2020-01-01"), _p("fresh", "Fresh", "2026-06-10")]
    stale = stale_candidates(pages, today="2026-06-15", max_age_days=180)
    assert "old" in stale and "fresh" not in stale


def test_stale_missing_updated_flagged() -> None:
    assert "noupd" in stale_candidates([_p("noupd", "NoUpd", "")], today="2026-06-15", max_age_days=180)


def test_merge_candidates_by_title_similarity() -> None:
    pages = [_p("rag", "RAG"), _p("rag-1", "RAG"), _p("other", "전혀 다른 주제")]
    pairs = merge_candidates(pages, threshold=0.9)
    flat = {frozenset(p) for p in pairs}
    assert frozenset({"rag", "rag-1"}) in flat
