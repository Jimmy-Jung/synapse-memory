"""Compatibility exports for provider-only retrieval.

저자: Synapse Memory Maintainers
작성일: 2026-06-16
"""
from __future__ import annotations

from synapse_memory.llm import ai_api
from synapse_memory.retrieval.index import (
    DEFAULT_MAX_PAGES,
    MAX_DOC_CHARS,
    AIEnv,
    SelectableIndex,
    select_related,
)

__all__ = [
    "DEFAULT_MAX_PAGES",
    "MAX_DOC_CHARS",
    "AIEnv",
    "SelectableIndex",
    "ai_api",
    "select_related",
]

