"""일일 파이프라인 진행률 status 기록.

위치: ``~/.synapse/run/daily.status.json``

다른 터미널이나 AI agent(Claude Code 데스크탑, Codex 등)에서 진행 상황을
polling으로 확인할 수 있도록 atomic write로 갱신한다. stdout이 부모 프로세스에
캡처되어 가려진 상태에서도 파일을 읽으면 현재 stage / 클러스터를 즉시 알 수 있다.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUS_DIR = Path.home() / ".synapse" / "run"
STATUS_FILE = STATUS_DIR / "daily.status.json"
LOCK_FILE = STATUS_DIR / "daily.lock"

_TMP_PREFIX = ".daily.status-"
_TMP_SUFFIX = ".tmp"


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


@dataclass
class DailyStatus:
    pid: int
    started_at: str
    updated_at: str
    state: str = "running"  # running | done | failed
    current_stage: str = ""
    current_stage_index: int = 0
    total_stages: int = 0
    stage_started_at: str = ""
    current_item: str = ""
    current_item_index: int = 0
    current_item_total: int = 0
    completed_stages: list[str] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class StatusSink:
    """no-op sink — 테스트나 status 비활성화 옵션에서 사용."""

    def begin_stage(self, name: str, index: int) -> None: ...
    def update_item(self, *, index: int, total: int, label: str) -> None: ...
    def end_stage(self, name: str, *, failed: bool = False) -> None: ...
    def finish(self, *, errors: int) -> None: ...


class DailyAlreadyRunningError(RuntimeError):
    """다른 daily 프로세스가 같은 machine-local pipeline을 실행 중."""


class DailyRunLock:
    """daily 중복 실행 방지용 advisory file lock.

    wiki/status 파일 같은 machine-local write surface는 동시 실행에 취약하다.
    lock 획득 실패 시 기존 pid를 포함해 즉시 실패시킨다.
    """

    def __init__(self, *, path: Path | None = None, pid: int | None = None) -> None:
        self._path = path if path is not None else LOCK_FILE
        self._pid = pid if pid is not None else os.getpid()
        self._fd: int | None = None

    def __enter__(self) -> DailyRunLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            existing = _read_lock_pid(self._path)
            os.close(fd)
            detail = f"pid {existing}" if existing is not None else str(self._path)
            raise DailyAlreadyRunningError(
                f"daily already running ({detail})"
            ) from exc
        os.ftruncate(fd, 0)
        os.write(fd, f"{self._pid}\n".encode())
        os.fsync(fd)
        self._fd = fd
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is None:
            return
        with contextlib.suppress(OSError):
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(self._fd)
        with contextlib.suppress(OSError):
            self._path.unlink()
        self._fd = None


def _read_lock_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text) if text else None
    except (OSError, ValueError):
        return None


class StatusWriter(StatusSink):
    """daily 진행 상태를 atomic하게 status JSON 파일에 기록.

    모든 IO 에러를 swallow하므로 daily 실행을 절대 막지 않는다.
    """

    def __init__(
        self,
        *,
        total_stages: int,
        path: Path | None = None,
        clock: Callable[[], str] = _utc_now_iso,
        pid: int | None = None,
    ) -> None:
        # path=None일 때 module-level STATUS_FILE을 lazy lookup해서
        # 테스트에서 monkeypatch로 위치를 바꿀 수 있게 한다.
        self._path = path if path is not None else STATUS_FILE
        self._clock = clock
        now = clock()
        self._status = DailyStatus(
            pid=pid if pid is not None else os.getpid(),
            started_at=now,
            updated_at=now,
            total_stages=total_stages,
        )
        self._write()

    def begin_stage(self, name: str, index: int) -> None:
        self._status.current_stage = name
        self._status.current_stage_index = index
        self._status.stage_started_at = self._clock()
        self._status.current_item = ""
        self._status.current_item_index = 0
        self._status.current_item_total = 0
        self._touch()

    def update_item(self, *, index: int, total: int, label: str) -> None:
        self._status.current_item = label
        self._status.current_item_index = index
        self._status.current_item_total = total
        self._touch()

    def end_stage(self, name: str, *, failed: bool = False) -> None:
        if failed:
            if name not in self._status.failed_stages:
                self._status.failed_stages.append(name)
        else:
            if name not in self._status.completed_stages:
                self._status.completed_stages.append(name)
        self._status.current_item = ""
        self._status.current_item_index = 0
        self._status.current_item_total = 0
        self._touch()

    def finish(self, *, errors: int) -> None:
        self._status.state = "failed" if errors else "done"
        self._status.current_stage = ""
        self._touch()

    @property
    def status(self) -> DailyStatus:
        return self._status

    def _touch(self) -> None:
        self._status.updated_at = self._clock()
        self._write()

    def _write(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._status.to_json()
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=_TMP_PREFIX,
                suffix=_TMP_SUFFIX,
                delete=False,
            ) as tmp:
                tmp.write(payload)
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, self._path)
        except Exception:
            # status write 실패는 daily 실행을 막지 않는다
            pass


def read_status(*, path: Path | None = None) -> DailyStatus | None:
    target = path if path is not None else STATUS_FILE
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception:
        return None
    try:
        data = json.loads(text)
        return DailyStatus(**data)
    except Exception:
        return None


def render_status(status: DailyStatus | None) -> str:
    """`synapse-memory daily-status` 용 사람이 읽기 좋은 출력."""
    if status is None:
        return "daily status 파일 없음 — 아직 실행한 적이 없거나 지워졌습니다."

    lines = [
        f"state:    {status.state}",
        f"pid:      {status.pid}",
        f"started:  {status.started_at}",
        f"updated:  {status.updated_at}",
    ]
    if status.current_stage:
        lines.append(
            f"stage:    {status.current_stage} "
            f"({status.current_stage_index}/{status.total_stages})"
        )
    if status.current_item_total:
        pct = int(status.current_item_index / status.current_item_total * 100)
        lines.append(
            f"item:     {status.current_item} "
            f"[{status.current_item_index}/{status.current_item_total}, {pct}%]"
        )
    if status.completed_stages:
        lines.append("completed: " + ", ".join(status.completed_stages))
    if status.failed_stages:
        lines.append("failed:    " + ", ".join(status.failed_stages))
    return "\n".join(lines)
