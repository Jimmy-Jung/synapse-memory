"""Cursor IDE mirror 테스트.

핵심 시나리오
- workspaceStorage / globalStorage SQLite 동시 mirror
- WAL/SHM 동반 파일 enumerate 제외
- logs/, History/ 디렉토리 제외
- idempotent (변경 없으면 files_unchanged 카운트)
- mtime+size 변경 시 backup 후 sha256 비교
- 누락 Cursor home → errors 1, files_scanned 0
- L0 권한
- daily.py stage wiring

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import json
import sqlite3
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.cursor.mirror import (
    META_DIR,
    STATES_FILE,
    collect_cursor,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def cursor_home(tmp_path: Path) -> Path:
    home = tmp_path / "cursor-user"
    (home / "workspaceStorage" / "abc123").mkdir(parents=True)
    (home / "globalStorage").mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    (home / "History").mkdir(parents=True)
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "cursor"


def _make_sqlite(path: Path, key: str = "k", value: bytes = b"v") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT, value BLOB)")
        conn.execute("INSERT INTO ItemTable VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def _read_sqlite_rows(path: Path) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return list(conn.execute("SELECT key, value FROM ItemTable"))
    finally:
        conn.close()


class TestCollectCursor:
    def test_mirrors_workspace_and_global(
        self, cursor_home: Path, dst_root: Path
    ) -> None:
        _make_sqlite(
            cursor_home / "workspaceStorage" / "abc123" / "state.vscdb",
            "ws", b"workspace-data",
        )
        _make_sqlite(
            cursor_home / "globalStorage" / "state.vscdb",
            "gl", b"global-data",
        )

        stats = collect_cursor(cursor_home=cursor_home, dst_root=dst_root)

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert stats.bytes_added > 0
        assert stats.errors == []

        ws_dst = dst_root / "workspaceStorage" / "abc123" / "state.vscdb"
        gl_dst = dst_root / "globalStorage" / "state.vscdb"
        assert ws_dst.is_file()
        assert gl_dst.is_file()
        # 백업이 실제 SQLite — 같은 row 가 읽혀야 함
        rows = _read_sqlite_rows(ws_dst)
        assert ("ws", b"workspace-data") in rows

    def test_excludes_wal_and_shm(
        self, cursor_home: Path, dst_root: Path
    ) -> None:
        ws_dir = cursor_home / "workspaceStorage" / "abc123"
        _make_sqlite(ws_dir / "state.vscdb", "x", b"y")
        (ws_dir / "state.vscdb-wal").write_bytes(b"wal stub")
        (ws_dir / "state.vscdb-shm").write_bytes(b"shm stub")

        stats = collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        assert stats.files_scanned == 1
        assert not (
            dst_root / "workspaceStorage" / "abc123" / "state.vscdb-wal"
        ).exists()
        assert not (
            dst_root / "workspaceStorage" / "abc123" / "state.vscdb-shm"
        ).exists()

    def test_excludes_logs_and_history(
        self, cursor_home: Path, dst_root: Path
    ) -> None:
        _make_sqlite(cursor_home / "logs" / "noise.vscdb", "n", b"x")
        _make_sqlite(cursor_home / "History" / "h.vscdb", "h", b"y")
        stats = collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        assert stats.files_scanned == 0
        assert not (dst_root / "logs").exists()
        assert not (dst_root / "History").exists()

    def test_idempotent(self, cursor_home: Path, dst_root: Path) -> None:
        _make_sqlite(
            cursor_home / "workspaceStorage" / "abc123" / "state.vscdb",
            "k", b"v",
        )
        s1 = collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        s2 = collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        assert s1.files_mirrored == 1
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, cursor_home: Path, dst_root: Path
    ) -> None:
        src = cursor_home / "workspaceStorage" / "abc123" / "state.vscdb"
        _make_sqlite(src, "k", b"v1")
        collect_cursor(cursor_home=cursor_home, dst_root=dst_root)

        conn = sqlite3.connect(str(src))
        try:
            conn.execute("INSERT INTO ItemTable VALUES (?, ?)", ("k2", b"v2"))
            conn.commit()
        finally:
            conn.close()

        s2 = collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        assert s2.files_mirrored == 1

    def test_missing_home_returns_error(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_cursor(
            cursor_home=tmp_path / "no-such-cursor",
            dst_root=dst_root,
        )
        assert len(stats.errors) == 1
        assert stats.files_scanned == 0

    def test_states_meta_written(
        self, cursor_home: Path, dst_root: Path
    ) -> None:
        _make_sqlite(
            cursor_home / "workspaceStorage" / "abc123" / "state.vscdb",
            "k", b"v",
        )
        collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        meta = dst_root / META_DIR / STATES_FILE
        assert meta.is_file()
        data = json.loads(meta.read_text(encoding="utf-8"))
        assert any(
            item["rel_path"] == "workspaceStorage/abc123/state.vscdb"
            for item in data
        )

    def test_l0_perms(self, cursor_home: Path, dst_root: Path) -> None:
        _make_sqlite(
            cursor_home / "workspaceStorage" / "abc123" / "state.vscdb",
            "k", b"v",
        )
        collect_cursor(cursor_home=cursor_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR).is_dir()


class TestDailyStageWiring:
    def test_collect_cursor_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_cursor" in STEPS
        assert any(
            s.name == "collect_cursor"
            and s.description == "Cursor IDE 로그 mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_cursor(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_cursor" in actions
        assert callable(actions["collect_cursor"])
