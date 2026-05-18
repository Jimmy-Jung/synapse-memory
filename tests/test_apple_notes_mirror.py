"""Apple Notes mirror 테스트.

핵심 시나리오
- NoteStore.sqlite backup
- WAL/SHM 동반 파일 무시
- idempotent / 변경 시 re-backup
- 누락 home → errors 1
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

from synapse_memory.collectors._sqlite_mirror import META_DIR, STATES_FILE
from synapse_memory.collectors.apple_notes.mirror import collect_apple_notes
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def notes_home(tmp_path: Path) -> Path:
    home = tmp_path / "group.com.apple.notes"
    home.mkdir(parents=True)
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "apple-notes"


def _make_notestore(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE ZICCLOUDSYNCINGOBJECT "
            "(Z_PK INTEGER PRIMARY KEY, ZTITLE TEXT)"
        )
        conn.execute(
            "INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (?, ?)",
            (1, "Test Note"),
        )
        conn.commit()
    finally:
        conn.close()


class TestCollectAppleNotes:
    def test_mirrors_notestore(
        self, notes_home: Path, dst_root: Path
    ) -> None:
        _make_notestore(notes_home / "NoteStore.sqlite")
        stats = collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        assert stats.files_scanned == 1
        assert stats.files_mirrored == 1
        dst_db = dst_root / "NoteStore.sqlite"
        assert dst_db.is_file()
        conn = sqlite3.connect(str(dst_db))
        try:
            rows = list(
                conn.execute("SELECT ZTITLE FROM ZICCLOUDSYNCINGOBJECT")
            )
        finally:
            conn.close()
        assert rows == [("Test Note",)]

    def test_ignores_wal_shm(
        self, notes_home: Path, dst_root: Path
    ) -> None:
        _make_notestore(notes_home / "NoteStore.sqlite")
        (notes_home / "NoteStore.sqlite-wal").write_bytes(b"wal stub")
        (notes_home / "NoteStore.sqlite-shm").write_bytes(b"shm stub")
        stats = collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        assert stats.files_scanned == 1

    def test_idempotent(self, notes_home: Path, dst_root: Path) -> None:
        _make_notestore(notes_home / "NoteStore.sqlite")
        collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        s2 = collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, notes_home: Path, dst_root: Path
    ) -> None:
        path = notes_home / "NoteStore.sqlite"
        _make_notestore(path)
        collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (?, ?)",
                (2, "Another Note"),
            )
            conn.commit()
        finally:
            conn.close()
        s2 = collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        assert s2.files_mirrored == 1

    def test_missing_home_returns_error(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_apple_notes(
            notes_home=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert len(stats.errors) == 1

    def test_l0_perms(self, notes_home: Path, dst_root: Path) -> None:
        _make_notestore(notes_home / "NoteStore.sqlite")
        collect_apple_notes(notes_home=notes_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_apple_notes_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_apple_notes" in STEPS
        assert any(
            s.name == "collect_apple_notes"
            and s.description == "Apple Notes mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_apple_notes(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_apple_notes" in actions
        assert callable(actions["collect_apple_notes"])
