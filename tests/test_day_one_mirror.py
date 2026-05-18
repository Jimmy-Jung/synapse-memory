"""Day One mirror 테스트.

핵심 시나리오
- 명시적 home → SQLite mirror
- env 로 home 지정
- nonexistent home → errors 1
- idempotent
- L0 권한
- daily wiring

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors._sqlite_mirror import META_DIR
from synapse_memory.collectors.day_one.mirror import collect_day_one
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def dayone_home(tmp_path: Path) -> Path:
    home = tmp_path / "5U8NS4GX82.dayoneapp2"
    (home / "Data" / "Documents").mkdir(parents=True)
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "day-one"


def _make_journal(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE ZENTRY "
            "(Z_PK INTEGER PRIMARY KEY, ZCREATIONDATE REAL, ZMARKDOWNTEXT TEXT)"
        )
        conn.execute(
            "INSERT INTO ZENTRY VALUES (?, ?, ?)",
            (1, 1715610000.0, "오늘 일기"),
        )
        conn.commit()
    finally:
        conn.close()


class TestCollectDayOne:
    def test_mirrors_with_explicit_home(
        self, dayone_home: Path, dst_root: Path
    ) -> None:
        _make_journal(dayone_home / "Data" / "Documents" / "DayOne.sqlite")
        stats = collect_day_one(dayone_home=dayone_home, dst_root=dst_root)
        assert stats.files_scanned == 1
        assert stats.files_mirrored == 1
        dst_db = dst_root / "Data" / "Documents" / "DayOne.sqlite"
        assert dst_db.is_file()

    def test_env_override(
        self, dayone_home: Path, dst_root: Path
    ) -> None:
        _make_journal(dayone_home / "Data" / "Documents" / "DayOne.sqlite")
        stats = collect_day_one(
            dayone_home_env=str(dayone_home),
            dst_root=dst_root,
        )
        assert stats.files_mirrored == 1

    def test_nonexistent_explicit_home_returns_error(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_day_one(
            dayone_home=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert len(stats.errors) == 1

    def test_idempotent(
        self, dayone_home: Path, dst_root: Path
    ) -> None:
        _make_journal(dayone_home / "Data" / "Documents" / "DayOne.sqlite")
        collect_day_one(dayone_home=dayone_home, dst_root=dst_root)
        s2 = collect_day_one(dayone_home=dayone_home, dst_root=dst_root)
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_korean_preserved(
        self, dayone_home: Path, dst_root: Path
    ) -> None:
        path = dayone_home / "Data" / "Documents" / "DayOne.sqlite"
        _make_journal(path)
        collect_day_one(dayone_home=dayone_home, dst_root=dst_root)
        dst_db = dst_root / "Data" / "Documents" / "DayOne.sqlite"
        conn = sqlite3.connect(str(dst_db))
        try:
            rows = list(conn.execute("SELECT ZMARKDOWNTEXT FROM ZENTRY"))
        finally:
            conn.close()
        assert rows == [("오늘 일기",)]

    def test_l0_perms(self, dayone_home: Path, dst_root: Path) -> None:
        _make_journal(dayone_home / "Data" / "Documents" / "DayOne.sqlite")
        collect_day_one(dayone_home=dayone_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR).is_dir()


class TestDailyStageWiring:
    def test_collect_day_one_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_day_one" in STEPS
        assert any(
            s.name == "collect_day_one"
            and s.description == "Day One journal mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_day_one(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_day_one" in actions
        assert callable(actions["collect_day_one"])
