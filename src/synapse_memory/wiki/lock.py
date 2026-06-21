# src/synapse_memory/wiki/lock.py
"""단일 동시성 락 — watch 사이클이 겹쳐 돌지 않도록 PID 기반 파일락.

PID 생존 확인(``os.kill(pid, 0)``)으로 죽은 프로세스가 남긴 stale 락은 재획득한다.
살아있는 프로세스가 보유 중이면 ``LockHeldError``.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

from synapse_memory.storage.l0 import l0_root

T = TypeVar("T")


class LockHeldError(RuntimeError):
    """락이 살아있는 다른 프로세스에 의해 보유 중일 때."""


class IngestAlreadyRunningError(RuntimeError):
    """manual/backfill ingest가 공유 ingest lock 때문에 시작하지 못했을 때."""

    def __init__(self, source: str, mode: str) -> None:
        super().__init__(
            f"ingest already running for source={source} mode={mode}; retry later "
            "or use --wait-lock where supported"
        )
        self.source = source
        self.mode = mode


@dataclass(frozen=True)
class LockedOutcome:
    source: str
    mode: str
    reason: str = "locked"


def default_lock_path() -> Path:
    """기본 락 경로 — L0 루트 아래 ``ingest.lock``."""
    return l0_root() / "ingest.lock"


def _pid_alive(pid: int) -> bool:
    """``pid`` 프로세스가 살아있는지 확인."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 시그널 권한은 없지만 프로세스는 존재 → 살아있음.
        return True
    except OSError:
        return False
    return True


class FileLock:
    """PID 기록 파일을 이용한 단순 단일 인스턴스 락."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> FileLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # 기존 락 — holder 생존 확인
            holder = self._read_pid()
            if holder is not None and _pid_alive(holder):
                raise LockHeldError(
                    f"ingest already running (pid {holder})"
                ) from None
            # stale: 제거 후 1회 재시도
            self._path.unlink(missing_ok=True)
            try:
                fd = os.open(
                    str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
            except FileExistsError as exc:
                raise LockHeldError(
                    "lock 경쟁 — 다른 프로세스가 방금 획득"
                ) from exc
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return self

    def release(self) -> None:
        if self._read_pid() == os.getpid():
            self._path.unlink(missing_ok=True)

    def _read_pid(self) -> int | None:
        try:
            return int(self._path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def __enter__(self) -> FileLock:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()


def run_with_ingest_lock(
    *,
    source: str,
    mode: str,
    on_locked: Literal["skip", "fail", "wait"],
    operation: Callable[[], T],
    lock_path: Path | None = None,
    retry_interval_seconds: float = 0.2,
) -> T | LockedOutcome:
    """모든 ingest writer가 공유하는 lock wrapper."""
    target = lock_path or default_lock_path()
    while True:
        try:
            with FileLock(target):
                return operation()
        except LockHeldError:
            if on_locked == "skip":
                return LockedOutcome(source=source, mode=mode)
            if on_locked == "fail":
                raise IngestAlreadyRunningError(source, mode) from None
            time.sleep(retry_interval_seconds)
