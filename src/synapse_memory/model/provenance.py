"""Immutable typed-edge evidence without raw conversation text.

Author: JunyoungJung
Created: 2026-09-22
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, fields
from typing import Any

from synapse_memory.model.schema import relation_fields


def _has_control(value: str) -> bool:
    return any(unicodedata.category(char).startswith("C") for char in value)


def normalize_relation_target(ref: str) -> str:
    """Remove a wikilink/alias wrapper while preserving a type:slug prefix."""
    if not isinstance(ref, str) or _has_control(ref) or "/" in ref or "\\" in ref:
        raise ValueError("relation_evidence target must be a safe relation reference")
    target = ref.strip()
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2]
    target = target.split("|", 1)[0].strip()
    if not target or "[" in target or "]" in target:
        raise ValueError("relation_evidence target must be a non-empty relation reference")
    return target


@dataclass(frozen=True)
class RelationEvidence:
    """A verified span within a local provider mirror, using exclusive end offsets."""

    relation: str
    target: str
    source: str
    start_byte: int
    end_byte: int
    start_char: int
    end_char: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.relation, str) or self.relation not in relation_fields():
            raise ValueError("relation_evidence relation must be a typed relation")
        object.__setattr__(self, "target", normalize_relation_target(self.target))
        if not isinstance(self.source, str) or _has_control(self.source):
            raise ValueError("relation_evidence source must be a provider-relative JSONL path")
        provider, _, path = self.source.partition(":")
        if (provider not in ("claude-code", "codex") or not path.endswith(".jsonl")
                or "\\" in path or ":" in path
                or any(part in ("", ".", "..") for part in path.split("/"))):
            raise ValueError("relation_evidence source must be a provider-relative JSONL path")
        offsets = (self.start_byte, self.end_byte, self.start_char, self.end_char)
        if any(type(value) is not int for value in offsets):
            raise ValueError("relation_evidence offsets must be integers")
        if not (0 <= self.start_byte < self.end_byte and 0 <= self.start_char < self.end_char):
            raise ValueError("relation_evidence offsets must describe non-empty ranges")
        if not isinstance(self.sha256, str) or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("relation_evidence sha256 must contain 64 lowercase hex digits")


def parse_relation_evidence(value: Any) -> tuple[RelationEvidence, ...]:
    """Parse a strict evidence collection; reject extra fields including raw quotes."""
    if not isinstance(value, (tuple, list)):
        raise ValueError("relation_evidence must be a list")
    parsed: list[RelationEvidence] = []
    required = {field.name for field in fields(RelationEvidence)}
    for item in value:
        if isinstance(item, RelationEvidence):
            parsed.append(item)
        elif isinstance(item, dict) and set(item) == required:
            parsed.append(RelationEvidence(**item))
        else:
            raise ValueError("relation_evidence requires exactly the declared evidence fields")
    return tuple(parsed)
