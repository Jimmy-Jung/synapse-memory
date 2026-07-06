from __future__ import annotations

import synapse_memory.cli as cli
from synapse_memory.wiki.page import WikiPage, load_page, save_page


def test_run_lint_fixes_links(tmp_path):
    save_page(WikiPage(type="concept", slug="a", title="A", related=("[[b]]",)), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="b", title="B"), vault_path=tmp_path)
    from synapse_memory.wiki.lint import run_lint
    report = run_lint(vault_path=tmp_path, today="2026-06-15")
    assert report.backlinks_added >= 1
    assert "[[a]]" in load_page("concept", "b", vault_path=tmp_path).related


def test_cli_lint_now(monkeypatch, capsys):
    from synapse_memory.wiki.lint import LintReport
    monkeypatch.setattr(cli, "run_lint", lambda **kw: LintReport(backlinks_added=2, dead_links_removed=1))
    assert cli.main(["lint", "--now"]) == 0
    assert "2" in capsys.readouterr().out
