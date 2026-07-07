from __future__ import annotations

import synapse_memory.cli as cli
from synapse_memory.model import Entity
from synapse_memory.wiki.page import load_page, save_page


def test_run_lint_fixes_links(tmp_path):
    save_page(
        Entity(type="concept", slug="a", title="A", related=("[[ghost]]", "[[b]]")),
        vault_path=tmp_path,
    )
    save_page(Entity(type="concept", slug="b", title="B"), vault_path=tmp_path)
    from synapse_memory.wiki.lint import run_lint
    report = run_lint(vault_path=tmp_path, today="2026-06-15")
    assert report.dead_links_removed >= 1
    assert "[[ghost]]" not in load_page("concept", "a", vault_path=tmp_path).related


def test_cli_lint_now(monkeypatch, capsys):
    from synapse_memory.wiki.lint import LintReport
    monkeypatch.setattr(cli, "run_lint", lambda **kw: LintReport(dead_links_removed=2))
    assert cli.main(["lint", "--now"]) == 0
    assert "2" in capsys.readouterr().out
