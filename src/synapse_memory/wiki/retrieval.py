# src/synapse_memory/wiki/retrieval.py
"""관련 기존 페이지 선별 (R2 부분구현: 이름매칭 + 1-hop).

의미유사도 top-k는 P2(rag 재조준)에서 추가. 여기서는 임베딩 없이
페이지 title/slug의 본문 등장 + 그 페이지의 related 1-hop 이웃만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.page import (
    VALID_TYPES,
    WikiPage,
    extract_wikilinks,
    list_pages,
)

DEFAULT_MAX_PAGES = 12


def _all_pages(vault_path: Path | None) -> list[WikiPage]:
    pages: list[WikiPage] = []
    for t in VALID_TYPES:
        pages.extend(list_pages(t, vault_path=vault_path))
    return pages


def _find_page_by_slug(slug: str, pages: list[WikiPage]) -> WikiPage | None:
    for p in pages:
        if p.slug == slug:
            return p
    return None


def find_related_pages(
    text: str,
    *,
    vault_path: Path | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[WikiPage]:
    """본문과 관련된 기존 페이지. 이름(title/slug) 등장 매칭 + related 1-hop.

    반환 순서: 직접 매칭 먼저(등장), 그다음 1-hop 이웃. slug 기준 dedup. max_pages 상한.
    """
    haystack = text.lower()
    all_pages = _all_pages(vault_path)

    matched: list[WikiPage] = []
    matched_slugs: set[str] = set()
    for p in all_pages:
        if p.slug in matched_slugs:
            continue
        if p.title.lower() in haystack or p.slug.lower() in haystack:
            matched.append(p)
            matched_slugs.add(p.slug)

    neighbors: list[WikiPage] = []
    for p in matched:
        for link in p.related:
            for target in (extract_wikilinks(link) or [link.strip("[]")]):
                if target in matched_slugs:
                    continue
                neighbor = _find_page_by_slug(target, all_pages)
                if neighbor is not None:
                    neighbors.append(neighbor)
                    matched_slugs.add(target)

    return (matched + neighbors)[:max_pages]
