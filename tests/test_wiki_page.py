"""WikiPage 모델 round-trip + 검증."""
from __future__ import annotations

import pytest

from synapse_memory.wiki.page import (
    WikiPage,
    parse_page,
    serialize_page,
)


def test_serialize_parse_round_trip() -> None:
    page = WikiPage(
        type="project",
        slug="synapse-memory",
        title="Synapse Memory",
        related=("[[obsidian]]", "[[rag]]"),
        sources=("claude_code:2026-06-14/sess-abc",),
        updated="2026-06-14",
        status="active",
        body="# Synapse Memory\n\n세컨드브레인 도구.\n",
    )
    text = serialize_page(page)
    assert text.startswith("---\n")
    restored = parse_page(text)
    assert restored == page


def test_parse_requires_frontmatter() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_page("frontmatter 없는 본문")


def test_parse_rejects_unknown_type() -> None:
    text = "---\ntype: wibble\nslug: x\ntitle: X\n---\n\nbody"
    with pytest.raises(ValueError, match="type"):
        parse_page(text)


def test_parse_requires_slug_and_title() -> None:
    text = "---\ntype: concept\nslug: x\n---\n\nbody"
    with pytest.raises(ValueError, match="title"):
        parse_page(text)
