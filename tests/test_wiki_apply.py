# tests/test_wiki_apply.py
"""apply_ops: save_page + 양방향 링크 + updated 스탬프."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.apply import apply_ops
from synapse_memory.wiki.integration import PageOp
from synapse_memory.wiki.page import WikiPage, load_page, save_page


def test_apply_creates_page_and_stamps_updated(tmp_path: Path) -> None:
    op = PageOp(op="create", page=WikiPage(type="concept", slug="rag", title="RAG", body="b"))
    written = apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    assert written == ["rag"]
    saved = load_page("concept", "rag", vault_path=tmp_path)
    assert saved.body.strip() == "b"
    assert saved.updated == "2026-06-14"


def test_apply_adds_back_link(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    op = PageOp(op="create", page=WikiPage(type="project", slug="synapse-memory",
                title="Synapse Memory", related=("[[rag]]",), body="b"))
    apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    rag = load_page("concept", "rag", vault_path=tmp_path)
    assert "[[synapse-memory]]" in rag.related


def test_apply_skips_backlink_when_target_missing(tmp_path: Path) -> None:
    op = PageOp(op="create", page=WikiPage(type="project", slug="p", title="P",
                related=("[[ghost]]",), body="b"))
    written = apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    assert written == ["p"]


def test_apply_update_preserves_existing_sources_and_related(tmp_path: Path) -> None:
    save_page(
        WikiPage(
            type="project",
            slug="tablet",
            title="Tablet",
            related=("[[ai-profile]]",),
            sources=("vault-md:tablet.md", "codex:old-session"),
            body="old body",
        ),
        vault_path=tmp_path,
    )
    op = PageOp(
        op="update",
        page=WikiPage(
            type="project",
            slug="tablet",
            title="Tablet",
            related=("[[ai-ide-ios-workflow]]",),
            sources=("codex:new-session",),
            body="new body",
        ),
    )

    apply_ops([op], vault_path=tmp_path, today="2026-06-20")

    saved = load_page("project", "tablet", vault_path=tmp_path)
    assert saved.body == "new body"
    assert saved.updated == "2026-06-20"
    assert saved.related == ("[[ai-profile]]", "[[ai-ide-ios-workflow]]")
    assert saved.sources == (
        "vault-md:tablet.md",
        "codex:old-session",
        "codex:new-session",
    )
