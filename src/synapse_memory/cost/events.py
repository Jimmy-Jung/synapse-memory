"""CostEvent model and append-only JSONL storage."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    ensure_secure_file,
    l0_root,
)

CostProvider: TypeAlias = Literal["claude", "codex"]
CostStatus: TypeAlias = Literal["success", "error", "timeout", "unavailable"]

COST_FILENAME = "cost.jsonl"
COMMAND_ENV_VAR = "SYNAPSE_COMMAND"
PROHIBITED_FIELDS = frozenset(
    {
        "prompt",
        "response",
        "content",
        "body",
        "document",
        "stderr",
        "stdout",
        "reason",
        "token",
        "api_key",
        "oauth",
    }
)


@dataclass(frozen=True)
class CostEvent:
    event_id: str
    ts: str
    command: str
    provider: CostProvider
    model: str
    status: CostStatus
    input_tokens: int
    output_tokens: int
    usd: float
    pricing_source: str
    elapsed_s: float
    error_kind: str | None = None

    def __post_init__(self) -> None:
        _validate_text("event_id", self.event_id)
        _validate_text("ts", self.ts)
        _validate_text("command", self.command)
        _validate_text("model", self.model)
        _validate_text("pricing_source", self.pricing_source)
        _validate_non_negative_int("input_tokens", self.input_tokens)
        _validate_non_negative_int("output_tokens", self.output_tokens)
        _validate_non_negative_number("usd", self.usd)
        _validate_non_negative_number("elapsed_s", self.elapsed_s)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        _reject_prohibited_fields(data)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CostEvent:
        _reject_prohibited_fields(data)
        return cls(
            event_id=str(data["event_id"]),
            ts=str(data["ts"]),
            command=str(data["command"]),
            provider=_as_provider(data["provider"]),
            model=str(data["model"]),
            status=_as_status(data["status"]),
            input_tokens=_as_int(data["input_tokens"]),
            output_tokens=_as_int(data["output_tokens"]),
            usd=_as_float(data["usd"]),
            pricing_source=str(data["pricing_source"]),
            elapsed_s=_as_float(data["elapsed_s"]),
            error_kind=str(data["error_kind"]) if data.get("error_kind") is not None else None,
        )


def cost_log_path() -> Path:
    ensure_l0_root_secure()
    return l0_root() / COST_FILENAME


def new_event_id(now: datetime | None = None) -> str:
    resolved = now or datetime.now(UTC)
    stamp = resolved.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def current_command(default: str = "unknown") -> str:
    return os.environ.get(COMMAND_ENV_VAR, "").strip() or default


@contextlib.contextmanager
def command_context(command: str) -> Iterator[None]:
    previous = os.environ.get(COMMAND_ENV_VAR)
    os.environ[COMMAND_ENV_VAR] = command
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(COMMAND_ENV_VAR, None)
        else:
            os.environ[COMMAND_ENV_VAR] = previous


def build_cost_event(
    *,
    command: str | None = None,
    provider: CostProvider,
    model: str,
    status: CostStatus,
    input_tokens: int,
    output_tokens: int,
    usd: float,
    pricing_source: str,
    elapsed_s: float,
    error_kind: str | None = None,
    now: datetime | None = None,
) -> CostEvent:
    resolved_now = now or datetime.now(UTC)
    resolved_command = current_command() if command is None else command
    return CostEvent(
        event_id=new_event_id(resolved_now),
        ts=resolved_now.isoformat().replace("+00:00", "Z"),
        command=resolved_command,
        provider=provider,
        model=model,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usd=round(float(usd), 8),
        pricing_source=pricing_source,
        elapsed_s=round(float(elapsed_s), 4),
        error_kind=error_kind,
    )


def append_cost_event(
    event: CostEvent,
    *,
    path: Path | None = None,
) -> Path:
    resolved = (path or cost_log_path()).expanduser().resolve()
    ensure_secure_dir(resolved.parent)
    line = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    fd = os.open(resolved, flags, L0_FILE_MODE)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        ensure_secure_file(resolved)
    return resolved


def load_cost_events(
    *,
    path: Path | None = None,
    recover: bool = False,
) -> list[CostEvent]:
    resolved = (path or cost_log_path()).expanduser().resolve()
    if not resolved.is_file():
        return []

    lines = resolved.read_text(encoding="utf-8").splitlines(keepends=True)
    events: list[CostEvent] = []
    good_lines: list[str] = []
    for index, line in enumerate(lines):
        try:
            event = CostEvent.from_dict(json.loads(line))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            if recover:
                _backup_corrupt_tail(resolved, lines, good_lines, index)
                return events
            raise
        events.append(event)
        good_lines.append(line)
    return events


def _backup_corrupt_tail(
    path: Path,
    lines: list[str],
    good_lines: list[str],
    first_bad_index: int,
) -> None:
    backup = path.with_name(f"{path.name}.bak.{new_event_id()}")
    backup.write_text("".join(lines[first_bad_index:]), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(backup, L0_FILE_MODE)
    path.write_text("".join(good_lines), encoding="utf-8")
    ensure_secure_file(path)
    if not backup.exists():
        shutil.copy2(path, backup)


def _validate_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _validate_non_negative_int(name: str, value: int) -> None:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _validate_non_negative_number(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a non-negative number")


def _reject_prohibited_fields(data: dict[str, object]) -> None:
    present = PROHIBITED_FIELDS.intersection(data)
    if present:
        raise ValueError(f"prohibited cost event fields: {sorted(present)}")


def _as_provider(value: object) -> CostProvider:
    if value in {"claude", "codex"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"unknown provider: {value}")


def _as_status(value: object) -> CostStatus:
    if value in {"success", "error", "timeout", "unavailable"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"unknown status: {value}")


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"not an integer: {value!r}")


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid number")
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError(f"not a number: {value!r}")
