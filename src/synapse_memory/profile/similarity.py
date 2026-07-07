"""Shared text normalization and token similarity helpers.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

import re

TRAILING_PUNCT = ".。!?:,;・…"


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, and strip trailing punctuation."""
    value = re.sub(r"\s+", " ", text).strip().lower()
    while value and value[-1] in TRAILING_PUNCT:
        value = value[:-1].rstrip()
    return value


def token_set(text: str) -> frozenset[str]:
    normalized = normalize(text)
    if not normalized:
        return frozenset()
    return frozenset(token for token in normalized.split() if token)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0
