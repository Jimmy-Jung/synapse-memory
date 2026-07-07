# src/synapse_memory/wiki/retrieval.py
"""관련 기존 Entity 선별 (R2 부분구현: 이름매칭 + 1-hop).

의미유사도 top-k는 P2(rag 재조준)에서 추가. 여기서는 임베딩 없이
Entity title/slug의 본문 등장 + related/typed relation 1-hop 이웃만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from synapse_memory.model import Entity
from synapse_memory.retrieval.page_index import build_page_index
from synapse_memory.retrieval.pages import _all_pages
from synapse_memory.retrieval.semantic import retrieve_items
from synapse_memory.wiki.links import extract_wikilinks, neighbor_links

DEFAULT_MAX_PAGES = 12

# semantic_fn 미지정 vs None(끄기)을 구분하기 위한 sentinel.
_DEFAULT = object()

SemanticFn = Callable[..., list[str]]


def _find_page_by_slug(slug: str, pages: list[Entity]) -> Entity | None:
    for p in pages:
        if p.slug == slug:
            return p
    return None


def _expand_neighbors(
    seeds: list[Entity],
    matched_slugs: set[str],
    all_pages: list[Entity],
) -> list[Entity]:
    """seeds의 related/typed relation 1-hop 이웃을 (이미 매칭된 것 제외) 수집."""
    neighbors: list[Entity] = []
    for p in seeds:
        for link in neighbor_links(p):
            for target in (extract_wikilinks(link) or [link.strip("[]")]):
                if target in matched_slugs:
                    continue
                neighbor = _find_page_by_slug(target, all_pages)
                if neighbor is not None:
                    neighbors.append(neighbor)
                    matched_slugs.add(target)
    return neighbors


def find_related_pages(
    text: str,
    *,
    vault_path: Path | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    semantic_fn: SemanticFn | None = _DEFAULT,  # type: ignore[assignment]
    pages: list[Entity] | None = None,
) -> list[Entity]:
    """본문과 관련된 기존 페이지. 이름(title/slug) 매칭 + 의미 top-k + related 1-hop.

    의미검색 토글:
        - ``semantic_fn`` 미지정 → provider 선별 사용 (rag 부재 시 graceful ``[]``).
        - ``semantic_fn=None`` → 의미검색 끄기 (이름매칭 + 1-hop만).
        - 함수 → 그 함수를 사용.

    반환 순서: 이름매칭 먼저, 그다음 의미 top-k, 그다음 1-hop 이웃.
    slug 기준 dedup. max_pages 상한.
    """
    haystack = text.lower()
    all_pages = pages if pages is not None else _all_pages(vault_path)

    matched: list[Entity] = []
    matched_slugs: set[str] = set()
    for p in all_pages:
        if p.slug in matched_slugs:
            continue
        if p.title.lower() in haystack or p.slug.lower() in haystack:
            matched.append(p)
            matched_slugs.add(p.slug)

    if semantic_fn is not None:
        # 기본(provider) 경로는 재로드 방지 위해 pages 주입. 커스텀 semantic_fn은
        # 기존 (text, vault_path, top_k) 계약 유지.
        if semantic_fn is _DEFAULT:
            semantic_pages = retrieve_items(
                text,
                all_pages,
                build_index=build_page_index,
                item_id=lambda page: page.slug,
                top_k=max_pages,
            )
        else:
            semantic_slugs = semantic_fn(text, vault_path=vault_path, top_k=max_pages)
            semantic_pages = [
                page
                for slug in semantic_slugs
                if (page := _find_page_by_slug(slug, all_pages)) is not None
            ]
        for page in semantic_pages:
            if page.slug in matched_slugs:
                continue
            matched.append(page)
            matched_slugs.add(page.slug)

    neighbors = _expand_neighbors(matched, matched_slugs, all_pages)
    return (matched + neighbors)[:max_pages]
