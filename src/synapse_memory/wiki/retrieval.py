# src/synapse_memory/wiki/retrieval.py
"""관련 기존 Entity 선별 (R2 부분구현: 이름매칭 + 1-hop).

의미유사도 top-k는 P2(rag 재조준)에서 추가. 여기서는 임베딩 없이
Entity title/slug의 본문 등장 + related/typed relation 1-hop 이웃만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from synapse_memory.llm import ai_api
from synapse_memory.model import Entity, current_entities, supersedes_history
from synapse_memory.retrieval.page_index import build_page_index
from synapse_memory.retrieval.pages import _all_pages
from synapse_memory.retrieval.semantic import retrieve_items
from synapse_memory.wiki.links import link_target, reverse_relations, typed_neighbors

DEFAULT_MAX_PAGES = 12
REVERSE_RELATION_SOURCE_LIMIT = 5
TRANSITIVE_RELATIONS = ("part_of", "broader")
SYMMETRIC_RELATIONS = ("same_as",)
TRANSITIVE_DEPTH = 2

# semantic_fn 미지정 vs None(끄기)을 구분하기 위한 sentinel.
_DEFAULT = object()

SemanticFn = Callable[..., list[str]]
AIEnv = ai_api.AIEnvironment | ai_api.AIProviderEnv | None


def _find_page_by_slug(slug: str, pages: list[Entity]) -> Entity | None:
    for p in pages:
        if p.slug == slug:
            return p
    return None


def _query_relation_filter(text: str) -> set[str]:
    haystack = text.lower()
    tokens = set(re.findall(r"[a-z0-9_]+", haystack))
    relations: set[str] = set()
    # ponytail: keyword intent heuristic, 오탐 상한 존재. 정밀 의도분류는 후속.
    if "uses" in tokens or "사용" in haystack:
        relations.add("uses")
    if "decided_in" in tokens or "decision" in tokens or "결정" in haystack:
        relations.add("decided_in")
    if "part_of" in tokens or "속한" in haystack or "상위" in haystack:
        relations.add("part_of")
    return relations


def _append_neighbor(
    neighbors: list[Entity],
    matched_slugs: set[str],
    all_pages: list[Entity],
    target: str,
) -> bool:
    if target in matched_slugs:
        return False
    neighbor = _find_page_by_slug(target, all_pages)
    if neighbor is None:
        return False
    neighbors.append(neighbor)
    matched_slugs.add(target)
    return True


def _expand_transitive(
    seed: Entity,
    all_pages: list[Entity],
    neighbors: list[Entity],
    matched_slugs: set[str],
    *,
    depth: int,
) -> None:
    """part_of/broader를 seed에서 forward로 depth 홉까지 따라가며 append (cycle-safe)."""
    frontier = [seed]
    walked = {seed.slug}
    for _ in range(depth):
        nxt: list[Entity] = []
        for page in frontier:
            grouped = typed_neighbors(page)
            for relation in TRANSITIVE_RELATIONS:
                for target in grouped.get(relation, ()):
                    _append_neighbor(neighbors, matched_slugs, all_pages, target)
                    if target not in walked:
                        walked.add(target)
                        found = _find_page_by_slug(target, all_pages)
                        if found is not None:
                            nxt.append(found)
        frontier = nxt


def _expand_neighbors(
    text: str,
    seeds: list[Entity],
    matched_slugs: set[str],
    all_pages: list[Entity],
) -> list[Entity]:
    """seeds의 typed/transitive/symmetric/reverse/related 이웃을 가중 순서로 수집."""
    neighbors: list[Entity] = []
    reverse_filter = _query_relation_filter(text)
    # same_as(대칭)가 없고 질의 의도도 없으면 역인덱스 계산을 건너뛴다(lazy).
    needs_reverse = bool(reverse_filter) or any(
        getattr(page, "same_as", ()) for page in all_pages
    )
    reverse_index = reverse_relations(all_pages) if needs_reverse else {}
    for page in seeds:
        for targets in typed_neighbors(page).values():
            for target in targets:
                _append_neighbor(neighbors, matched_slugs, all_pages, target)
        # part_of/broader 이행 폐쇄 (depth<=2, 폭주 방지 캡)
        _expand_transitive(page, all_pages, neighbors, matched_slugs, depth=TRANSITIVE_DEPTH)
        # same_as는 대칭(identity) — 역방향도 무조건 확장
        for relation, source in reverse_index.get(page.slug, ()):
            if relation in SYMMETRIC_RELATIONS:
                _append_neighbor(neighbors, matched_slugs, all_pages, source)
        # 질의 의도(uses/decided_in/part_of)일 때만 역방향 확장, relation별 상한
        if reverse_filter:
            reverse_counts: dict[str, int] = {}
            for relation, source in reverse_index.get(page.slug, ()):
                if relation in reverse_filter:
                    if reverse_counts.get(relation, 0) >= REVERSE_RELATION_SOURCE_LIMIT:
                        continue
                    if _append_neighbor(neighbors, matched_slugs, all_pages, source):
                        reverse_counts[relation] = reverse_counts.get(relation, 0) + 1
        for link in getattr(page, "related", ()):
            _append_neighbor(neighbors, matched_slugs, all_pages, link_target(str(link)))
    return neighbors


def expand_related_pages(
    text: str,
    seeds: list[Entity],
    all_pages: list[Entity],
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[Entity]:
    """Expand already-selected seed pages with weighted relation neighbors."""
    matched_slugs = {page.slug for page in seeds}
    neighbors = _expand_neighbors(text, seeds, matched_slugs, all_pages)
    return (seeds + neighbors)[:max_pages]


def expand_supersedes_history(
    seeds: list[Entity],
    all_pages: list[Entity],
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[Entity]:
    """Append supersedes chains for already-selected current pages."""
    expanded: list[Entity] = []
    seen: set[str] = set()
    for page in seeds:
        chain = supersedes_history(all_pages, f"{page.type}:{page.slug}") or (page,)
        for entity in chain:
            key = f"{entity.type}:{entity.slug}"
            if key in seen:
                continue
            expanded.append(entity)
            seen.add(key)
            if len(expanded) >= max_pages:
                return expanded
    return expanded


def find_related_pages(
    text: str,
    *,
    vault_path: Path | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    semantic_fn: SemanticFn | None = _DEFAULT,  # type: ignore[assignment]
    pages: list[Entity] | None = None,
    include_history: bool = False,
    exclude_types: tuple[str, ...] = (),
    ai_env: AIEnv = None,
) -> list[Entity]:
    """본문과 관련된 기존 페이지. 이름(title/slug) 매칭 + 의미 top-k + related 1-hop.

    ``exclude_types``: 제외할 entity type (예: ("log",) — episodic 제외 semantic 검색,
    CQ12). 기본 빈 튜플 = 전 타입 포함 (ingest가 log 갱신 대상을 찾아야 하므로 불변).

    의미검색 토글:
        - ``semantic_fn`` 미지정 → provider 선별 사용 (rag 부재 시 graceful ``[]``).
        - ``semantic_fn=None`` → 의미검색 끄기 (이름매칭 + 1-hop만).
        - 함수 → 그 함수를 사용.

    반환 순서: 이름매칭 먼저, 그다음 의미 top-k, 그다음 1-hop 이웃.
    slug 기준 dedup. max_pages 상한.
    """
    haystack = text.lower()
    all_pages = (
        pages
        if pages is not None
        else _all_pages(vault_path, include_history=include_history)
    )
    if not include_history:
        all_pages = list(current_entities(all_pages))
    if exclude_types:
        all_pages = [p for p in all_pages if p.type not in exclude_types]

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
                env=ai_env,
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

    return expand_related_pages(text, matched, all_pages, max_pages=max_pages)
