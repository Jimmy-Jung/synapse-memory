"""Unit tests for v2 wiki doctor checks (diagnose_wiki_pages / diagnose_wiki_maintenance)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from synapse_memory.doctor import (
    DiagnosticStatus,
    diagnose_wiki_maintenance,
    diagnose_wiki_pages,
)


def test_wiki_pages_warn_when_no_pages(tmp_path: Path) -> None:
    result = diagnose_wiki_pages(tmp_path)

    assert result.status == DiagnosticStatus.WARN
    assert "0개" in result.message


def test_wiki_pages_ok_when_pages_present(tmp_path: Path) -> None:
    # config.vault_folders.wiki.concepts 기본값 "Concepts" 폴더에 페이지 1개 배치.
    concepts = tmp_path / "Concepts"
    concepts.mkdir(parents=True)
    (concepts / "topic.md").write_text(
        "---\ntype: concept\nslug: topic\ntitle: Topic\n---\n\n본문\n",
        encoding="utf-8",
    )

    result = diagnose_wiki_pages(tmp_path)

    assert result.status == DiagnosticStatus.OK
    assert "페이지" in result.message


def test_wiki_maintenance_warn_when_daemon_absent(tmp_path: Path) -> None:
    result = diagnose_wiki_maintenance(home=tmp_path)

    assert result.status == DiagnosticStatus.WARN
    assert "watch" in result.message


def test_wiki_maintenance_ok_when_plist_present(tmp_path: Path) -> None:
    from synapse_memory.wiki.launchd import plist_path

    path = plist_path(home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<plist></plist>", encoding="utf-8")
    state = tmp_path / "state.json"
    now = datetime.now().astimezone().isoformat()
    state.write_text(
        f'{{"claude-code": "{now}", "codex": "{now}"}}',
        encoding="utf-8",
    )

    result = diagnose_wiki_maintenance(home=tmp_path, state_path=state)

    assert result.status == DiagnosticStatus.OK
    assert str(path) in result.message


def test_wiki_maintenance_warns_on_stale_watermark(tmp_path: Path) -> None:
    from synapse_memory.wiki.launchd import plist_path

    path = plist_path(home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<plist></plist>", encoding="utf-8")
    stale = (datetime.now().astimezone() - timedelta(days=30)).isoformat()
    state = tmp_path / "state.json"
    state.write_text(
        f'{{"claude-code": "{stale}", "codex": "{stale}"}}',
        encoding="utf-8",
    )

    result = diagnose_wiki_maintenance(home=tmp_path, state_path=state)

    assert result.status == DiagnosticStatus.WARN
    assert "stale" in result.message


def test_wiki_maintenance_reports_recent_watch_errors(tmp_path: Path) -> None:
    from synapse_memory.wiki.launchd import plist_path

    path = plist_path(home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<plist></plist>", encoding="utf-8")
    state = tmp_path / "state.json"
    now = datetime.now().astimezone().isoformat()
    state.write_text(
        f'{{"claude-code": "{now}", "codex": "{now}"}}',
        encoding="utf-8",
    )
    err = tmp_path / "watch.err.log"
    err.write_text("provider failed\n", encoding="utf-8")

    result = diagnose_wiki_maintenance(
        home=tmp_path,
        state_path=state,
        err_log_path=err,
    )

    assert result.status == DiagnosticStatus.WARN
    assert "watch.err.log" in result.message
