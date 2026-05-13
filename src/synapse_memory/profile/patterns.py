"""DecisionPatterns.md read helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config

_FIELD_RE = re.compile(r"^\s*(?:[-*]\s*)?(trigger|action|rationale|confidence):\s*(.+?)\s*$")


@dataclass(frozen=True)
class DecisionPatternReference:
    pattern_id: str
    trigger: str
    action: str
    display_name: str


def list_decision_patterns(*, vault_path: Path | None = None) -> list[DecisionPatternReference]:
    path = _patterns_path(vault_path)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        match = _FIELD_RE.match(line)
        if match is None:
            continue
        key, value = match.groups()
        if key == "trigger" and current.get("trigger") and current.get("action"):
            records.append(current)
            current = {}
        current[key] = value
    if current.get("trigger") and current.get("action"):
        records.append(current)

    patterns: list[DecisionPatternReference] = []
    for record in records:
        trigger = record["trigger"]
        action = record["action"]
        patterns.append(
            DecisionPatternReference(
                pattern_id=_pattern_id(trigger, action),
                trigger=trigger,
                action=action,
                display_name=f"{trigger} -> {action}",
            )
        )
    return patterns


def find_decision_pattern(
    pattern_id: str, *, vault_path: Path | None = None
) -> DecisionPatternReference | None:
    return next(
        (p for p in list_decision_patterns(vault_path=vault_path) if p.pattern_id == pattern_id),
        None,
    )


def _pattern_id(trigger: str, action: str) -> str:
    digest = hashlib.sha1(f"{trigger}|{action}".encode()).hexdigest()[:12]
    return f"pattern-{digest}"


def _patterns_path(vault_path: Path | None) -> Path:
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / get_config().vault_folders.system.ai.decision_patterns
