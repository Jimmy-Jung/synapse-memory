"""Last AI answer metadata storage for feedback commands."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from synapse_memory.feedback.events import new_event_id
from synapse_memory.storage.l0 import ensure_l0_root_secure, l0_root, secure_write_text

AnswerCommand: TypeAlias = str
"""Open string alias. Recognized values: "ask", "persona.what_did_i_think", "persona.decide",
and dynamic "persona.generate.<recipe_name>" identifiers introduced by 007-persona-recipes.
Validation in :func:`LastAnswerReference.from_dict` accepts any non-empty string.

Legacy command identifiers from pre-rename (`me.what_did_i_think`, `me.decide`,
`me.generate.*`) are auto-migrated to the `persona.*` form on load — see
``_normalize_legacy_command``. Writes always use the new form."""


def _normalize_legacy_command(cmd: str) -> str:
    """pre-M1a rename 시점 의 `me.*` command 식별자를 `persona.*` 로 변환.

    M1a 는 backward-compat 의도로 내부 식별자를 보존했으나, deep rename 결정 후
    legacy file 을 silent 마이그레이션 한다. 새 파일은 항상 `persona.*` 로 기록.
    """
    if cmd.startswith("me."):
        return "persona." + cmd[len("me.") :]
    return cmd

CitationTargetKind: TypeAlias = Literal["card", "pattern"]
LAST_RESPONSE_FILENAME = "last_response.json"


@dataclass(frozen=True)
class AnswerCitation:
    target_kind: CitationTargetKind
    target_ref: str
    source_kind: str
    display_name: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AnswerCitation:
        target_kind = data.get("target_kind")
        if target_kind not in {"card", "pattern"}:
            raise ValueError(f"unknown target_kind: {target_kind}")
        return cls(
            target_kind=target_kind,  # type: ignore[arg-type]
            target_ref=str(data["target_ref"]),
            source_kind=str(data.get("source_kind", "")),
            display_name=str(data.get("display_name", "")),
        )


@dataclass(frozen=True)
class LastAnswerReference:
    answer_id: str
    ts: str
    command: AnswerCommand
    query: str
    citations: tuple[AnswerCitation, ...]
    session_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "answer_id": self.answer_id,
            "ts": self.ts,
            "command": self.command,
            "query": self.query,
            "session_id": self.session_id,
            "citations": [c.to_dict() for c in self.citations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LastAnswerReference:
        command = data.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"command must be non-empty string, got {command!r}")
        command = _normalize_legacy_command(command)
        raw_citations = data.get("citations", [])
        if not isinstance(raw_citations, list):
            raise ValueError("citations must be a list")
        return cls(
            answer_id=str(data["answer_id"]),
            ts=str(data["ts"]),
            command=command,
            query=str(data.get("query", "")),
            citations=tuple(
                AnswerCitation.from_dict(c)
                for c in raw_citations
                if isinstance(c, dict)
            ),
            session_id=(
                str(data["session_id"]) if data.get("session_id") is not None else None
            ),
        )


def last_response_path() -> Path:
    ensure_l0_root_secure()
    return l0_root() / LAST_RESPONSE_FILENAME


def save_last_answer(ref: LastAnswerReference, *, path: Path | None = None) -> Path:
    resolved = (path or last_response_path()).expanduser().resolve()
    return secure_write_text(
        resolved,
        json.dumps(ref.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )


def load_last_answer(*, path: Path | None = None) -> LastAnswerReference | None:
    resolved = (path or last_response_path()).expanduser().resolve()
    if not resolved.is_file():
        return None
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return LastAnswerReference.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def new_answer_reference(
    *,
    command: AnswerCommand,
    query: str,
    citations: tuple[AnswerCitation, ...],
    session_id: str | None = None,
) -> LastAnswerReference:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return LastAnswerReference(
        answer_id=new_event_id(now),
        ts=now.isoformat().replace("+00:00", "Z"),
        command=command,
        query=query,
        citations=citations,
        session_id=session_id,
    )
