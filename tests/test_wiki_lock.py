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
    with FileLock(p), pytest.raises(LockHeldError), FileLock(p):
        pass


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path: Path) -> None:
    p = tmp_path / "ingest.lock"
    p.write_text("999999999", encoding="utf-8")  # 없는 PID
    with FileLock(p):
        pass


def test_live_pid_lock_raises_stale_is_reclaimed(tmp_path: Path) -> None:
    # Arrange: 살아있는 PID(현재 프로세스)가 보유한 락
    import os

    p = tmp_path / "ingest.lock"
    p.write_text(str(os.getpid()), encoding="utf-8")

    # Act & Assert: live holder → 획득 실패
    with pytest.raises(LockHeldError):
        FileLock(p).acquire()

    # Arrange: stale(죽은 PID)로 교체
    p.write_text("999999999", encoding="utf-8")

    # Act & Assert: stale → 재획득 성공
    lock = FileLock(p).acquire()
    assert p.read_text(encoding="utf-8") == str(os.getpid())
    lock.release()
