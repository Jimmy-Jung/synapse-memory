# src/synapse_memory/wiki/lock.py
"""단일 동시성 락 — watch 사이클이 겹쳐 돌지 않도록 PID 기반 파일락.

PID 생존 확인(``os.kill(pid, 0)``)으로 죽은 프로세스가 남긴 stale 락은 재획득한다.
살아있는 프로세스가 보유 중이면 ``LockHeldError``.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

import os
from pathlib import Path

from synapse_memory.storage.l0 import l0_root


class LockHeldError(RuntimeError):
    """락이 살아있는 다른 프로세스에 의해 보유 중일 때."""


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
        if self._path.exists():
            holder = self._read_pid()
            if holder is not None and _pid_alive(holder):
                raise LockHeldError(
                    f"락 보유 중 (pid={holder}): {self._path}"
                )
            # stale(죽은 PID 또는 파싱 실패) → 덮어쓴다.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(str(os.getpid()), encoding="utf-8")
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
