"""FeedbackEvent model and append-only JSONL storage."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias

from synapse_memory.redaction.pass1 import redact
from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    ensure_secure_file,
    l0_root,
)

FeedbackTargetKind: TypeAlias = Literal["answer", "card", "pattern"]
FeedbackAction: TypeAlias = Literal["accept", "reject", "weight"]

FEEDBACK_FILENAME = "feedback.jsonl"
MAX_REASON_CHARS = 500


@dataclass(frozen=True)
class FeedbackEvent:
    event_id: str
    ts: str
    target_kind: FeedbackTargetKind
    target_ref: str
    action: FeedbackAction
    weight: float
    reason: str | None = None
    answer_id_context: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FeedbackEvent:
        raw_weight = data["weight"]
        if not isinstance(raw_weight, (str, int, float)):
            raise ValueError("weight must be numeric")
        return cls(
            event_id=str(data["event_id"]),
            ts=str(data["ts"]),
            target_kind=_as_target_kind(data["target_kind"]),
            target_ref=str(data["target_ref"]),
            action=_as_action(data["action"]),
            weight=float(raw_weight),
            reason=str(data["reason"]) if data.get("reason") is not None else None,
            answer_id_context=(
                str(data["answer_id_context"])
                if data.get("answer_id_context") is not None
                else None
            ),
        )


def feedback_log_path() -> Path:
    ensure_l0_root_secure()
    return l0_root() / FEEDBACK_FILENAME


def new_event_id(now: datetime | None = None) -> str:
    resolved = now or datetime.now(UTC)
    stamp = resolved.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def build_feedback_event(
    *,
    target_kind: FeedbackTargetKind,
    target_ref: str,
    action: FeedbackAction,
    reason: str | None = None,
    weight: float | None = None,
    answer_id_context: str | None = None,
    now: datetime | None = None,
) -> FeedbackEvent:
    if not target_ref.strip():
        raise ValueError("target_ref는 빈 문자열일 수 없음")

    resolved_weight = _resolve_weight(action, weight)
    resolved_reason = _sanitize_reason(reason)
    if action == "reject" and not resolved_reason:
        raise ValueError("reject feedback reason is required")

    ts = (now or datetime.now(UTC)).isoformat().replace("+00:00", "Z")
    return FeedbackEvent(
        event_id=new_event_id(now),
        ts=ts,
        target_kind=target_kind,
        target_ref=target_ref,
        action=action,
        weight=resolved_weight,
        reason=resolved_reason,
        answer_id_context=answer_id_context,
    )


def append_feedback_event(
    event: FeedbackEvent,
    *,
    path: Path | None = None,
) -> Path:
    resolved = (path or feedback_log_path()).expanduser().resolve()
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


def load_feedback_events(
    *,
    path: Path | None = None,
    recover: bool = False,
) -> list[FeedbackEvent]:
    resolved = (path or feedback_log_path()).expanduser().resolve()
    if not resolved.is_file():
        return []

    lines = resolved.read_text(encoding="utf-8").splitlines(keepends=True)
    events: list[FeedbackEvent] = []
    good_lines: list[str] = []
    for index, line in enumerate(lines):
        try:
            event = FeedbackEvent.from_dict(json.loads(line))
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


def _resolve_weight(action: FeedbackAction, weight: float | None) -> float:
    if action == "accept":
        value = 0.2 if weight is None else weight
    elif action == "reject":
        value = -0.3 if weight is None else weight
    else:
        if weight is None:
            raise ValueError("weight action requires weight")
        value = weight
    if not -1.0 <= value <= 1.0:
        raise ValueError("weight must be between -1.0 and 1.0")
    return round(value, 4)


def _sanitize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    stripped = reason.strip()
    if not stripped:
        return None
    return redact(stripped[:MAX_REASON_CHARS]).redacted


def _as_target_kind(value: object) -> FeedbackTargetKind:
    if value in {"answer", "card", "pattern"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"unknown target_kind: {value}")


def _as_action(value: object) -> FeedbackAction:
    if value in {"accept", "reject", "weight"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"unknown action: {value}")
