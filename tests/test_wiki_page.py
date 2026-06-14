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


def test_parse_null_updated_and_status_fall_back() -> None:
    text = "---\ntype: concept\nslug: x\ntitle: X\nupdated:\nstatus:\n---\n\nbody"
    page = parse_page(text)
    assert page.updated == ""
    assert page.status == "active"


def test_parse_invalid_date_raises_valueerror() -> None:
    text = "---\ntype: concept\nslug: x\ntitle: X\nupdated: 2026-13-40\n---\n\nbody"
    with pytest.raises(ValueError, match="파싱 실패"):
        parse_page(text)


def test_all_valid_types_round_trip() -> None:
    from synapse_memory.wiki.page import VALID_TYPES
    for t in VALID_TYPES:
        page = WikiPage(type=t, slug="s", title="T", body="b")
        assert parse_page(serialize_page(page)) == page
