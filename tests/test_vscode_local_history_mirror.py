"""VS Code Local History mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.vscode_local_history.mirror import (
    META_DIR,
    STATES_FILE,
    collect_vscode_local_history,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def history_home(tmp_path: Path) -> Path:
    home = tmp_path / "History"
    (home / "abc123").mkdir(parents=True)
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "vscode-local-history"


class TestCollectVscodeLocalHistory:
    def test_mirrors_snapshots_and_entries(
        self, history_home: Path, dst_root: Path
    ) -> None:
        d = history_home / "abc123"
        (d / "1715610000.py").write_text("print('a')\n", encoding="utf-8")
        (d / "1715610100.py").write_text("print('b')\n", encoding="utf-8")
        (d / "entries.json").write_text(
            '{"resource":"file:///workspace/a.py","entries":[]}',
            encoding="utf-8",
        )

        stats = collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        assert stats.files_scanned == 3
        assert stats.files_mirrored == 3
        assert (dst_root / "abc123" / "1715610000.py").is_file()
        assert (dst_root / "abc123" / "entries.json").is_file()

    def test_silent_when_uninstalled(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_vscode_local_history(
            history_home=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_idempotent(self, history_home: Path, dst_root: Path) -> None:
        (history_home / "abc123" / "1.py").write_text("x", encoding="utf-8")
        collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        s2 = collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, history_home: Path, dst_root: Path
    ) -> None:
        src = history_home / "abc123" / "1.py"
        src.write_text("v1", encoding="utf-8")
        collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        src.write_text("v2 changed", encoding="utf-8")
        s2 = collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        assert s2.files_mirrored == 1

    def test_korean_preserved(
        self, history_home: Path, dst_root: Path
    ) -> None:
        (history_home / "abc123" / "k.py").write_text(
            "# 한글 주석\n", encoding="utf-8"
        )
        collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        assert "한글 주석" in (
            dst_root / "abc123" / "k.py"
        ).read_text(encoding="utf-8")

    def test_l0_perms(self, history_home: Path, dst_root: Path) -> None:
        (history_home / "abc123" / "1.py").write_text("x", encoding="utf-8")
        collect_vscode_local_history(
            history_home=history_home, dst_root=dst_root
        )
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_vscode_local_history_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_vscode_local_history" in STEPS
        assert any(
            s.name == "collect_vscode_local_history"
            and s.description == "VS Code Local History mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_vscode_local_history(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_vscode_local_history" in actions
        assert callable(actions["collect_vscode_local_history"])
