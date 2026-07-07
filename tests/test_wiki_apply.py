# tests/test_wiki_apply.py
"""apply_ops: save_page + updated 스탬프 + related 병합."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from synapse_memory.wiki.apply import apply_ops
from synapse_memory.wiki.integration import PageOp
from synapse_memory.wiki.lint import validate_schema_rules
from synapse_memory.wiki.page import WikiPage, load_page, save_page


def test_apply_creates_page_and_stamps_updated(tmp_path: Path) -> None:
    op = PageOp(op="create", page=WikiPage(type="concept", slug="rag", title="RAG", body="b"))
    written = apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    assert written == ["rag"]
    saved = load_page("concept", "rag", vault_path=tmp_path)
    assert saved.body.strip() == "b"
    assert saved.updated == "2026-06-14"
    assert saved.created == "2026-06-14"
    assert "created:" in (tmp_path / "Concepts" / "rag.md").read_text(encoding="utf-8")


def test_apply_creates_page_with_dead_related_link(tmp_path: Path) -> None:
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


def test_apply_update_preserves_existing_created(tmp_path: Path) -> None:
    save_page(
        WikiPage(
            type="project",
            slug="tablet",
            title="Tablet",
            created="2026-05-01",
            body="old body",
        ),
        vault_path=tmp_path,
    )
    op = PageOp(
        op="update",
        page=WikiPage(type="project", slug="tablet", title="Tablet", body="new body"),
    )

    apply_ops([op], vault_path=tmp_path, today="2026-06-20")

    saved = load_page("project", "tablet", vault_path=tmp_path)
    assert saved.created == "2026-05-01"
    assert saved.updated == "2026-06-20"


def test_apply_merges_typed_relations_and_keeps_schema_ranges_valid(
    tmp_path: Path,
) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    save_page(
        WikiPage(
            type="concept",
            slug="provider-retrieval",
            title="Provider Retrieval",
        ),
        vault_path=tmp_path,
    )
    save_page(
        WikiPage(type="project", slug="parent-project", title="Parent Project"),
        vault_path=tmp_path,
    )
    save_page(
        WikiPage(type="project", slug="old-project", title="Old Project"),
        vault_path=tmp_path,
    )
    save_page(
        WikiPage(
            type="project",
            slug="tablet-project-alias",
            title="Tablet Project Alias",
        ),
        vault_path=tmp_path,
    )
    save_page(
        WikiPage(
            type="insight",
            slug="decision-note",
            title="Decision Note",
            created="2026-07-07",
            updated="2026-07-07",
            observed_at="2026-07-07",
        ),
        vault_path=tmp_path,
    )
    save_page(
        WikiPage(
            type="log",
            slug="daily-log",
            title="Daily Log",
            created="2026-07-07",
            updated="2026-07-07",
            observed_at="2026-07-07",
        ),
        vault_path=tmp_path,
    )

    apply_ops(
        [
            PageOp(
                op="create",
                page=WikiPage(
                    type="project",
                    slug="tablet",
                    title="Tablet",
                    uses=("rag",),
                    part_of=("parent-project",),
                    about=("provider-retrieval",),
                    decided_in=("decision-note",),
                    supersedes=("old-project",),
                    same_as=("tablet-project-alias",),
                    body="created body",
                ),
            )
        ],
        vault_path=tmp_path,
        today="2026-07-07",
    )
    created_text = (tmp_path / "Entities/Projects/tablet.md").read_text(
        encoding="utf-8"
    )
    assert "uses:\n- rag\n" in created_text
    assert "decided_in:\n- decision-note\n" in created_text
    assert "related:" not in created_text

    apply_ops(
        [
            PageOp(
                op="update",
                page=WikiPage(
                    type="project",
                    slug="tablet",
                    title="Tablet",
                    uses=("provider-retrieval",),
                    decided_in=("daily-log",),
                    body="updated body",
                ),
            )
        ],
        vault_path=tmp_path,
        today="2026-07-08",
    )

    saved = load_page("project", "tablet", vault_path=tmp_path)
    assert saved.body == "updated body"
    assert saved.uses == ("rag", "provider-retrieval")
    assert saved.decided_in == ("decision-note", "daily-log")
    assert saved.part_of == ("parent-project",)
    assert saved.about == ("provider-retrieval",)
    assert saved.supersedes == ("old-project",)
    assert saved.same_as == ("tablet-project-alias",)
    assert validate_schema_rules(vault_path=tmp_path).validation_violations == ()


@pytest.mark.parametrize(
    ("page_type", "folder"),
    [
        ("insight", "Insights/2026/06"),
        ("log", "Logs/2026/06"),
    ],
)
def test_apply_create_stamps_observed_at_for_observed_types(
    tmp_path: Path, page_type: str, folder: str
) -> None:
    op = PageOp(
        op="create",
        page=WikiPage(type=page_type, slug="observed", title="Observed", body="b"),
    )

    apply_ops([op], vault_path=tmp_path, today="2026-06-14")

    saved = load_page(
        page_type,
        "observed",
        vault_path=tmp_path,
        when=date(2026, 6, 14),
    )
    text = (tmp_path / folder / "observed.md").read_text(encoding="utf-8")
    assert saved.created == "2026-06-14"
    assert saved.observed_at == "2026-06-14"
    assert "created:" in text
    assert "observed_at:" in text
