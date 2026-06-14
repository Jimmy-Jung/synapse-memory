from __future__ import annotations
from pathlib import Path
from synapse_memory.wiki.index_md import (
    MARKER_END, MARKER_START, index_md_path, render_index, write_index,
)
from synapse_memory.wiki.page import WikiPage


def test_index_md_path(tmp_path: Path) -> None:
    assert index_md_path(vault_path=tmp_path) == tmp_path / "index.md"


def test_render_lists_pages_and_review() -> None:
    pages = [WikiPage(type="project", slug="sm", title="SM")]
    body = render_index(pages, orphans=["sm"], review_items=[{"kind": "stale", "slug": "sm"}])
    assert "[[sm]]" in body
    assert "project" in body.lower()
    assert "stale" in body
    assert MARKER_START in body and MARKER_END in body


def test_write_preserves_user_content_outside_markers(tmp_path: Path) -> None:
    p = tmp_path / "index.md"
    p.write_text(f"내 메모\n{MARKER_START}\nOLD\n{MARKER_END}\n꼬리말\n", encoding="utf-8")
    write_index([WikiPage(type="concept", slug="x", title="X")], orphans=[], review_items=[], vault_path=tmp_path)
    text = p.read_text(encoding="utf-8")
    assert "내 메모" in text and "꼬리말" in text
    assert "OLD" not in text
    assert "[[x]]" in text
