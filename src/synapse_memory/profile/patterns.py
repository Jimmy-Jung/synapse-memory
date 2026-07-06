"""Decision pattern read helpers from the wiki profile page."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.profile.similarity import normalize
from synapse_memory.profile.wiki import profile_page_path

_FIELD_RE = re.compile(r"^\s*(?:[-*]\s*)?(trigger|action|rationale|confidence):\s*(.+?)\s*$")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)\s*$")
_ACTION_RE = re.compile(r"^\s*[-*]\s+행동:\s*(.+?)\s*$")


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
    patterns.extend(_parse_wiki_decision_patterns(text))
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
    return profile_page_path(vault_path)


def _parse_wiki_decision_patterns(text: str) -> list[DecisionPatternReference]:
    patterns: list[DecisionPatternReference] = []
    in_decision = False
    trigger = ""
    action = ""

    def flush() -> None:
        if trigger and action:
            patterns.append(
                DecisionPatternReference(
                    pattern_id=_pattern_id(trigger, action),
                    trigger=trigger,
                    action=action,
                    display_name=f"{trigger} -> {action}",
                )
            )

    for line in text.splitlines():
        h2 = _H2_RE.match(line)
        if h2:
            flush()
            trigger = ""
            action = ""
            in_decision = normalize(h2.group(1)).startswith("decision patterns")
            continue
        if not in_decision:
            continue
        h3 = _H3_RE.match(line)
        if h3:
            flush()
            trigger = h3.group(1).strip()
            action = ""
            continue
        match = _ACTION_RE.match(line)
        if match:
            action = match.group(1).strip()
    flush()
    return patterns
