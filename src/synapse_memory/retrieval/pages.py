"""Wiki page loading for retrieval callers.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.store import list_pages
from synapse_memory.wiki.page import VALID_TYPES, WikiPage


def _all_pages(vault_path: Path | None = None) -> list[WikiPage]:
    """전 타입 페이지 수집 (slug 알파벳순 — list_pages 보장)."""
    pages: list[WikiPage] = []
    for page_type in VALID_TYPES:
        pages.extend(list_pages(page_type, vault_path=vault_path))
    return pages
