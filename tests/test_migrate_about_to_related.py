"""about relation migration script tests.

Author: JunyoungJung
Created: 2026-07-07
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "migrate_about_to_related.py"
)
SPEC = importlib.util.spec_from_file_location("migrate_about_to_related", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
migrate_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migrate_script)


def _write_page(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n\nbody\n", encoding="utf-8")


def test_migrate_about_to_related_dry_run_does_not_mutate(tmp_path: Path) -> None:
    page = tmp_path / "Concepts" / "rag.md"
    _write_page(
        page,
        "type: concept\n"
        "slug: rag\n"
        "title: RAG\n"
        "related:\n"
        "- retrieval\n"
        "about:\n"
        "- retrieval\n"
        "- llm\n",
    )

    result = migrate_script.migrate_about_to_related(tmp_path, dry_run=True)

    assert result.changed == (page,)
    assert "about:" in page.read_text(encoding="utf-8")


def test_migrate_about_to_related_apply_is_idempotent(tmp_path: Path) -> None:
    page = tmp_path / "Concepts" / "rag.md"
    _write_page(
        page,
        "type: concept\n"
        "slug: rag\n"
        "title: RAG\n"
        "related:\n"
        "- retrieval\n"
        "about:\n"
        "- retrieval\n"
        "- llm\n",
    )

    first = migrate_script.migrate_about_to_related(tmp_path, dry_run=False)
    second = migrate_script.migrate_about_to_related(tmp_path, dry_run=False)

    text = page.read_text(encoding="utf-8")
    assert first.changed == (page,)
    assert second.changed == ()
    assert "about:" not in text
    assert "related:\n- retrieval\n- llm\n" in text
