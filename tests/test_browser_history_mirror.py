"""browser_history mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest

from synapse_memory.collectors.browser_history.mirror import (
    DEFAULT_BACKUP_TIMEOUT_SECONDS,
    META_DIR,
    STATES_FILE,
    BrowserSource,
    collect_browser_history,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "browser-history"


def _make_history_db(path: Path, browser: str = "chrome") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE urls "
            "(id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
            "visit_count INTEGER, last_visit_time INTEGER)"
        )
        conn.execute(
            "INSERT INTO urls VALUES (?, ?, ?, ?, ?)",
            (1, f"https://{browser}.example.com", "Example", 1, 1715610000),
        )
        conn.commit()
    finally:
        conn.close()


def _browser(tmp_path: Path, name: str) -> BrowserSource:
    db = tmp_path / name / "History"
    _make_history_db(db, browser=name)
    return BrowserSource(name=name, db_path=db)


class TestCollectBrowserHistory:
    def test_mirrors_multiple_browsers(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        browsers = (
            _browser(tmp_path, "chrome"),
            _browser(tmp_path, "safari"),
            _browser(tmp_path, "arc"),
        )
        stats = collect_browser_history(browsers=browsers, dst_root=dst_root)
        assert stats.browsers_scanned == 3
        assert stats.browsers_mirrored == 3
        for name in ("chrome", "safari", "arc"):
            assert (dst_root / name / "History").is_file()

    def test_silent_when_no_browsers_installed(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        browsers = (
            BrowserSource(name="chrome", db_path=tmp_path / "missing"),
        )
        stats = collect_browser_history(browsers=browsers, dst_root=dst_root)
        assert stats.browsers_scanned == 0
        assert stats.errors == []

    def test_idempotent(self, tmp_path: Path, dst_root: Path) -> None:
        browsers = (_browser(tmp_path, "chrome"),)
        collect_browser_history(browsers=browsers, dst_root=dst_root)
        s2 = collect_browser_history(browsers=browsers, dst_root=dst_root)
        assert s2.browsers_mirrored == 0
        assert s2.browsers_unchanged == 1

    def test_change_triggers_remirror(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        src = tmp_path / "chrome" / "History"
        _make_history_db(src)
        browsers = (BrowserSource(name="chrome", db_path=src),)
        collect_browser_history(browsers=browsers, dst_root=dst_root)
        conn = sqlite3.connect(str(src))
        try:
            conn.execute(
                "INSERT INTO urls VALUES (?, ?, ?, ?, ?)",
                (2, "https://x", "x", 1, 1715620000),
            )
            conn.commit()
        finally:
            conn.close()
        s2 = collect_browser_history(browsers=browsers, dst_root=dst_root)
        assert s2.browsers_mirrored == 1

    def test_backup_preserves_rows(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        browsers = (_browser(tmp_path, "chrome"),)
        collect_browser_history(browsers=browsers, dst_root=dst_root)
        conn = sqlite3.connect(str(dst_root / "chrome" / "History"))
        try:
            rows = list(conn.execute("SELECT url FROM urls"))
        finally:
            conn.close()
        assert rows == [("https://chrome.example.com",)]

    def test_l0_perms(self, tmp_path: Path, dst_root: Path) -> None:
        browsers = (_browser(tmp_path, "chrome"),)
        collect_browser_history(browsers=browsers, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()

    def test_backup_timeout_records_error_and_continues(
        self, tmp_path: Path, dst_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / "chrome" / "History"
        _make_history_db(src)
        browsers = (BrowserSource(name="chrome", db_path=src),)

        def fake_run(*_args: object, **kwargs: object) -> object:
            raise subprocess.TimeoutExpired(
                cmd="sqlite-backup",
                timeout=kwargs.get("timeout", DEFAULT_BACKUP_TIMEOUT_SECONDS),
            )

        monkeypatch.setattr(
            "synapse_memory.collectors.browser_history.mirror.subprocess.run",
            fake_run,
        )

        stats = collect_browser_history(
            browsers=browsers,
            dst_root=dst_root,
            backup_timeout_seconds=0.01,
        )

        assert stats.browsers_scanned == 1
        assert stats.browsers_mirrored == 0
        assert stats.browsers_unchanged == 0
        assert len(stats.errors) == 1
        assert stats.errors[0][0] == "chrome"
        assert "timed out" in stats.errors[0][1]
        assert not (dst_root / "chrome" / "History.tmp").exists()
        assert not (dst_root / "chrome" / "History").exists()


class TestDailyStageWiring:
    def test_collect_browser_history_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_browser_history" in STEPS
        assert any(
            s.name == "collect_browser_history"
            and s.description == "브라우저 history mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_browser_history(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_browser_history" in actions
        assert callable(actions["collect_browser_history"])
