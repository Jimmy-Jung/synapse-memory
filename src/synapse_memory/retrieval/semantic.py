"""Shared build-index → select helper.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from synapse_memory.llm import ai_api
from synapse_memory.retrieval.index import SelectableIndex, select_related

T = TypeVar("T")
AIEnv = ai_api.AIEnvironment | ai_api.AIProviderEnv | None


def retrieve_items(
    query: str,
    items: Sequence[T],
    *,
    build_index: Callable[[list[T]], SelectableIndex],
    item_id: Callable[[T], str],
    top_k: int,
    env: AIEnv = None,
) -> list[T]:
    """Build an index once, select IDs once, return matching items in provider order."""
    if not items:
        return []
    item_list = list(items)
    index = build_index(item_list)
    by_id = {item_id(item): item for item in item_list}
    selected = select_related(query, index, max_pages=top_k, env=env)
    return [by_id[slug] for slug in selected if slug in by_id]
