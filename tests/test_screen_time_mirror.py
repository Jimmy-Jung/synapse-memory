"""screen_time mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.screen_time.mirror import (
    META_DIR,
    STATES_FILE,
    collect_screen_time,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "knowledgeC.db"


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "screen-time"


def _make_knowledge_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE ZOBJECT "
            "(Z_PK INTEGER PRIMARY KEY, ZSTREAMNAME TEXT, ZVALUESTRING TEXT)"
        )
        conn.execute(
            "INSERT INTO ZOBJECT VALUES (?, ?, ?)",
            (1, "/app/usage", "com.apple.Safari"),
        )
        conn.commit()
    finally:
        conn.close()


class TestCollectScreenTime:
    def test_mirrors_db(self, db_path: Path, dst_root: Path) -> None:
        _make_knowledge_db(db_path)
        stats = collect_screen_time(db_path=db_path, dst_root=dst_root)
        assert stats.files_scanned == 1
        assert stats.files_mirrored == 1
        dst_db = dst_root / "knowledgeC.db"
        assert dst_db.is_file()
        conn = sqlite3.connect(str(dst_db))
        try:
            rows = list(conn.execute("SELECT ZSTREAMNAME FROM ZOBJECT"))
        finally:
            conn.close()
        assert rows == [("/app/usage",)]

    def test_silent_when_uninstalled(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_screen_time(
            db_path=tmp_path / "no-such.db", dst_root=dst_root
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_idempotent(self, db_path: Path, dst_root: Path) -> None:
        _make_knowledge_db(db_path)
        collect_screen_time(db_path=db_path, dst_root=dst_root)
        s2 = collect_screen_time(db_path=db_path, dst_root=dst_root)
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, db_path: Path, dst_root: Path
    ) -> None:
        _make_knowledge_db(db_path)
        collect_screen_time(db_path=db_path, dst_root=dst_root)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO ZOBJECT VALUES (?, ?, ?)",
                (2, "/app/usage", "com.apple.Notes"),
            )
            conn.commit()
        finally:
            conn.close()
        s2 = collect_screen_time(db_path=db_path, dst_root=dst_root)
        assert s2.files_mirrored == 1

    def test_l0_perms(self, db_path: Path, dst_root: Path) -> None:
        _make_knowledge_db(db_path)
        collect_screen_time(db_path=db_path, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_screen_time_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_screen_time" in STEPS
        assert any(
            s.name == "collect_screen_time"
            and s.description == "Screen Time (knowledgeC) mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_screen_time(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_screen_time" in actions
        assert callable(actions["collect_screen_time"])
