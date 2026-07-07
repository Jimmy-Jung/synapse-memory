# src/synapse_memory/wiki/apply.py
"""PageOp 목록을 vault에 적용 — save_page + updated 스탬프.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from synapse_memory.model import Entity
from synapse_memory.model.entity import OBSERVED_AT_TYPES, RELATION_FIELDS
from synapse_memory.store import load_page, save_page
from synapse_memory.wiki.integration import PageOp


def _merge_tuple(existing: tuple[str, ...], incoming: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in (*existing, *incoming):
        if value in seen:
            continue
        merged.append(value)
        seen.add(value)
    return tuple(merged)


def _stamped_page(page: Entity, *, stamp: str, existing: Entity | None) -> Entity:
    created = (existing.created if existing else "") or page.created or stamp
    observed_at = ""
    if page.type in OBSERVED_AT_TYPES:
        observed_at = (existing.observed_at if existing else "") or page.observed_at or created
    return replace(page, created=created, updated=stamp, observed_at=observed_at)


def _page_for_apply(page: Entity, op: str, *, vault_path: Path | None, stamp: str) -> Entity:
    if op != "update":
        return _stamped_page(page, stamp=stamp, existing=None)
    try:
        existing = load_page(page.type, page.slug, vault_path=vault_path)
    except (FileNotFoundError, ValueError):
        return _stamped_page(page, stamp=stamp, existing=None)
    stamped = _stamped_page(page, stamp=stamp, existing=existing)
    return replace(
        stamped,
        attrs={**existing.attrs, **stamped.attrs},
        related=_merge_tuple(existing.related, stamped.related),
        sources=_merge_tuple(existing.sources, stamped.sources),
        **{
            relation: _merge_tuple(
                tuple(getattr(existing, relation) or ()),
                tuple(getattr(stamped, relation) or ()),
            )
            for relation in RELATION_FIELDS
        },
    )


def apply_ops(
    ops: list[PageOp],
    *,
    vault_path: Path | None = None,
    today: str | None = None,
) -> list[str]:
    """ops 적용. 반환: 기록된 페이지 slug 목록 (순서 보존)."""
    stamp = today or date.today().isoformat()
    written: list[str] = []
    for op in ops:
        page = _page_for_apply(op.page, op.op, vault_path=vault_path, stamp=stamp)
        save_page(page, vault_path=vault_path)
        written.append(page.slug)
    return written
