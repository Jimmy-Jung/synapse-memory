"""Compatibility exports for shared PageIndex.

저자: Synapse Memory Maintainers
작성일: 2026-06-16
"""
from __future__ import annotations

from synapse_memory.retrieval.page_index import (
    DEFAULT_SUMMARY_CHARS,
    PageEntry,
    PageIndex,
    build_page_index,
)

__all__ = [
    "DEFAULT_SUMMARY_CHARS",
    "PageEntry",
    "PageIndex",
    "build_page_index",
]

