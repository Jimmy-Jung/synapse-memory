# src/synapse_memory/wiki/apply.py
"""PageOp 목록을 vault에 적용 — save_page + 양방향 링크 보강.

끊긴 링크 전체 점검(lint)은 P4. 여기서는 방금 추가한 related의 즉시 역링크만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from synapse_memory.wiki.integration import PageOp
from synapse_memory.wiki.page import (
    WikiPage,
    extract_wikilinks,
    load_page,
    save_page,
    with_related,
)


def _link_targets(page: WikiPage) -> list[str]:
    targets: list[str] = []
    for link in page.related:
        targets.extend(extract_wikilinks(link) or [link.strip("[]")])
    return targets


def _add_back_links(page: WikiPage, *, vault_path: Path | None) -> None:
    """page가 가리키는 각 대상에 page로의 역링크 추가 (대상 존재 시만)."""
    back = f"[[{page.slug}]]"
    for target_slug in _link_targets(page):
        for ptype in ("project", "company", "person", "concept", "profile"):
            try:
                target = load_page(ptype, target_slug, vault_path=vault_path)
            except (FileNotFoundError, ValueError):
                continue
            if back not in target.related:
                save_page(with_related(target, back), vault_path=vault_path)
            break


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
        page = replace(op.page, updated=stamp)
        save_page(page, vault_path=vault_path)
        written.append(page.slug)
        _add_back_links(page, vault_path=vault_path)
    return written
