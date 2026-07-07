"""Entity loading for retrieval callers.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.model import ENTITY_TYPES, Entity
from synapse_memory.store import list_pages


def _all_pages(vault_path: Path | None = None) -> list[Entity]:
    """전 타입 Entity 수집 (slug 알파벳순 — list_pages 보장)."""
    pages: list[Entity] = []
    for page_type in ENTITY_TYPES:
        pages.extend(list_pages(page_type, vault_path=vault_path))
    return pages
