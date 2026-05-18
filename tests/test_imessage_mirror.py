"""iMessage mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.imessage.mirror import (
    META_DIR,
    STATES_FILE,
    collect_imessage,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def messages_home(tmp_path: Path) -> Path:
    home = tmp_path / "Messages"
    home.mkdir()
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "imessage"


def _make_chat_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE message "
            "(ROWID INTEGER PRIMARY KEY, text TEXT, date INTEGER)"
        )
        conn.execute(
            "INSERT INTO message VALUES (?, ?, ?)",
            (1, "안녕 친구", 1715610000),
        )
        conn.commit()
    finally:
        conn.close()


class TestCollectImessage:
    def test_mirrors_chat_db(
        self, messages_home: Path, dst_root: Path
    ) -> None:
        _make_chat_db(messages_home / "chat.db")
        stats = collect_imessage(
            messages_home=messages_home, dst_root=dst_root
        )
        assert stats.files_scanned == 1
        assert stats.files_mirrored == 1
        dst_db = dst_root / "chat.db"
        assert dst_db.is_file()
        conn = sqlite3.connect(str(dst_db))
        try:
            rows = list(conn.execute("SELECT text FROM message"))
        finally:
            conn.close()
        assert rows == [("안녕 친구",)]

    def test_disable_env_opts_out(
        self, messages_home: Path, dst_root: Path
    ) -> None:
        _make_chat_db(messages_home / "chat.db")
        stats = collect_imessage(
            messages_home=messages_home,
            dst_root=dst_root,
            disable_env="1",
        )
        assert stats.files_scanned == 0
        assert stats.files_mirrored == 0
        assert not (dst_root / "chat.db").exists()

    def test_disable_env_falsy_values_pass_through(
        self, messages_home: Path, dst_root: Path
    ) -> None:
        _make_chat_db(messages_home / "chat.db")
        # 처음 호출 mirror
        s1 = collect_imessage(
            messages_home=messages_home,
            dst_root=dst_root,
            disable_env="0",
        )
        assert s1.files_scanned == 1
        # 후속 호출 unchanged
        for val in ("", "false", "no"):
            stats = collect_imessage(
                messages_home=messages_home,
                dst_root=dst_root,
                disable_env=val,
            )
            assert stats.files_scanned == 1

    def test_idempotent(
        self, messages_home: Path, dst_root: Path
    ) -> None:
        _make_chat_db(messages_home / "chat.db")
        collect_imessage(messages_home=messages_home, dst_root=dst_root)
        s2 = collect_imessage(messages_home=messages_home, dst_root=dst_root)
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_missing_home_returns_error(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_imessage(
            messages_home=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert len(stats.errors) == 1

    def test_l0_perms(self, messages_home: Path, dst_root: Path) -> None:
        _make_chat_db(messages_home / "chat.db")
        collect_imessage(messages_home=messages_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_imessage_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_imessage" in STEPS
        assert any(
            s.name == "collect_imessage"
            and s.description == "iMessage chat.db mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_imessage(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_imessage" in actions
        assert callable(actions["collect_imessage"])
