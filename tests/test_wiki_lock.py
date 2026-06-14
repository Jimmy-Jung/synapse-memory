"""FileLock: 단일 인스턴스 보장."""
from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.wiki.lock import FileLock, LockHeldError


def test_acquire_and_release(tmp_path: Path) -> None:
    with FileLock(tmp_path / "ingest.lock"):
        assert (tmp_path / "ingest.lock").exists()
    with FileLock(tmp_path / "ingest.lock"):  # 재획득 가능
        pass


def test_second_acquire_fails_while_held(tmp_path: Path) -> None:
    p = tmp_path / "ingest.lock"
    with FileLock(p):
        with pytest.raises(LockHeldError):
            with FileLock(p):
                pass


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path: Path) -> None:
    p = tmp_path / "ingest.lock"
    p.write_text("999999999", encoding="utf-8")  # 없는 PID
    with FileLock(p):
        pass
