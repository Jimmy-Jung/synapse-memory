from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.lint import apply_structural_fixes
from synapse_memory.wiki.page import WikiPage, load_page, save_page


def test_adds_missing_backlinks(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="a", title="A", related=("[[b]]",)), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="b", title="B"), vault_path=tmp_path)
    report = apply_structural_fixes(vault_path=tmp_path)
    assert report.backlinks_added >= 1
    assert "[[a]]" in load_page("concept", "b", vault_path=tmp_path).related


def test_removes_dead_links(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="a", title="A", related=("[[ghost]]", "[[b]]")), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="b", title="B"), vault_path=tmp_path)
    report = apply_structural_fixes(vault_path=tmp_path)
    a = load_page("concept", "a", vault_path=tmp_path)
    assert "[[ghost]]" not in a.related
    assert "[[b]]" in a.related
    assert report.dead_links_removed >= 1


def test_idempotent(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="a", title="A", related=("[[b]]",)), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="b", title="B"), vault_path=tmp_path)
    apply_structural_fixes(vault_path=tmp_path)
    second = apply_structural_fixes(vault_path=tmp_path)
    assert second.backlinks_added == 0
    assert second.dead_links_removed == 0
