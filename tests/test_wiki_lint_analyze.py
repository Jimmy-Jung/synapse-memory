"""구조 분석기 — 순수 함수 (디스크 불필요)."""
from __future__ import annotations

from synapse_memory.wiki.lint import find_broken_backlinks, find_dead_links, find_orphans
from synapse_memory.wiki.page import WikiPage


def _p(slug, related=()):
    return WikiPage(type="concept", slug=slug, title=slug.upper(), related=tuple(related))


def test_find_broken_backlinks() -> None:
    pages = [_p("a", ["[[b]]"]), _p("b")]
    broken = find_broken_backlinks(pages)
    assert ("b", "a") in [(s, t) for s, t in broken]  # b가 a로의 역링크 필요


def test_find_dead_links() -> None:
    pages = [_p("a", ["[[ghost]]", "[[b]]"]), _p("b")]
    dead = find_dead_links(pages)
    assert ("a", "ghost") in dead
    assert ("a", "b") not in dead


def test_find_orphans() -> None:
    pages = [_p("a", ["[[b]]"]), _p("b"), _p("lonely")]
    orphans = find_orphans(pages)
    assert "lonely" in orphans
    assert "b" not in orphans
    assert "a" not in orphans
