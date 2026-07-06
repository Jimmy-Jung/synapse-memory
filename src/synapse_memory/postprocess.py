"""Shared answer post-processing helpers."""

from __future__ import annotations

import re

_META_PREFIX_RE = re.compile(
    r"^\s*(?:Insight|Insights|Analysis|Observation|Thought|Note|Meta)\s*:\s*.*(?:\n+|$)",
    re.IGNORECASE,
)


def strip_meta_prefix(answer: str) -> str:
    """Remove leading Claude/Codex meta preambles without touching body text."""
    cleaned = answer
    while True:
        next_value = _META_PREFIX_RE.sub("", cleaned, count=1).lstrip()
        if next_value == cleaned:
            return cleaned
        cleaned = next_value
