"""Endpoint answer post-processing helpers.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import re

_META_PREFIX_RE = re.compile(
    r"^\s*(?:Insight|Insights|Analysis|Observation|Thought|Note|Meta)\s*:\s*.*(?:\n+|$)",
    re.IGNORECASE,
)


def strip_meta_prefix(answer: str) -> str:
    """Remove Claude Code meta preambles such as ``Insight: ...``.

    FR-A9 only targets leading meta commentary. Body content is left intact.
    """
    cleaned = answer
    while True:
        next_value = _META_PREFIX_RE.sub("", cleaned, count=1).lstrip()
        if next_value == cleaned:
            return cleaned
        cleaned = next_value
