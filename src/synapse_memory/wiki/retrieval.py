# src/synapse_memory/wiki/retrieval.py
"""관련 기존 페이지 선별 (R2 부분구현: 이름매칭 + 1-hop).

의미유사도 top-k는 P2(rag 재조준)에서 추가. 여기서는 임베딩 없이
페이지 title/slug의 본문 등장 + 그 페이지의 related 1-hop 이웃만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from synapse_memory.wiki.page import (
    VALID_TYPES,
    WikiPage,
    extract_wikilinks,
    list_pages,
)

DEFAULT_MAX_PAGES = 12

# semantic_fn 미지정 vs None(끄기)을 구분하기 위한 sentinel.
_DEFAULT = object()

SemanticFn = Callable[..., list[str]]


def _default_semantic(text: str, *, vault_path: Path | None, top_k: int) -> list[str]:
    """rag 의미검색으로 wiki 페이지 slug top-k를 반환. rag 부재/오류 시 ``[]``.

    빈/부재 store에서도 안전하게 ``[]``를 보장해 기존 회귀 테스트가
    실제 벡터 스토어를 건드리지 않게 한다.
    """
    try:
        from synapse_memory.rag import embed_query, open_vector_store

        store = open_vector_store()
        results = store.query(
            embed_query(text),
            top_k=top_k,
            where={"source_kind": "wiki"},
        )
        slugs: list[str] = []
        for rec, _dist in results:
            slug = (rec.metadata or {}).get("slug")
            if slug:
                slugs.append(str(slug))
        return slugs
    except Exception:
        return []


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


def _expand_neighbors(
    seeds: list[WikiPage],
    matched_slugs: set[str],
    all_pages: list[WikiPage],
) -> list[WikiPage]:
    """seeds의 related 1-hop 이웃을 (이미 매칭된 것 제외) 수집."""
    neighbors: list[WikiPage] = []
    for p in seeds:
        for link in p.related:
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
) -> list[WikiPage]:
    """본문과 관련된 기존 페이지. 이름(title/slug) 매칭 + 의미 top-k + related 1-hop.

    의미검색 토글:
        - ``semantic_fn`` 미지정 → ``_default_semantic`` 사용 (rag 부재 시 graceful ``[]``).
        - ``semantic_fn=None`` → 의미검색 끄기 (이름매칭 + 1-hop만).
        - 함수 → 그 함수를 사용.

    반환 순서: 이름매칭 먼저, 그다음 의미 top-k, 그다음 1-hop 이웃.
    slug 기준 dedup. max_pages 상한.
    """
    resolved_semantic: SemanticFn | None = (
        _default_semantic if semantic_fn is _DEFAULT else semantic_fn
    )

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

    if resolved_semantic is not None:
        semantic_slugs = resolved_semantic(
            text, vault_path=vault_path, top_k=max_pages
        )
        for slug in semantic_slugs:
            if slug in matched_slugs:
                continue
            page = _find_page_by_slug(slug, all_pages)
            if page is not None:
                matched.append(page)
                matched_slugs.add(slug)

    neighbors = _expand_neighbors(matched, matched_slugs, all_pages)
    return (matched + neighbors)[:max_pages]
