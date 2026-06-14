"""wiki lint — 구조 자동 수정 + 사람 검토 큐 (전부 순수 Python, LLM 불필요).

R3 원칙: "구조는 자동, 진실은 사람".
- 구조 결함(끊긴 역링크, 죽은 링크, 고아)은 자동 수정.
- 진위 판단이 필요한 것(낡음 의심, 병합 후보)은 index.md 검토 큐에 나열만.

분석기(find_*)는 list[WikiPage] 입력의 순수 함수 — 결정적, 디스크 불필요.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

from synapse_memory.wiki.page import WikiPage, extract_wikilinks


def _targets(page: WikiPage) -> list[str]:
    """page.related의 각 링크에서 slug 대상을 추출 (등장순, 중복 제거)."""
    seen: dict[str, None] = {}
    for link in page.related:
        extracted = extract_wikilinks(link) or [link.strip("[]").strip()]
        for target in extracted:
            if target and target not in seen:
                seen[target] = None
    return list(seen.keys())


def find_broken_backlinks(pages: list[WikiPage]) -> list[tuple[str, str]]:
    """A가 B를 링크하는데 B가 A를 링크 안 하면 (B, A) — B가 A로의 역링크 필요.

    B가 pages에 존재할 때만 보고한다.
    """
    by_slug = {p.slug: p for p in pages}
    targets_of = {p.slug: set(_targets(p)) for p in pages}
    broken: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        a = page.slug
        for b in _targets(page):
            if b not in by_slug:
                continue  # 죽은 링크는 find_dead_links 담당
            if a not in targets_of[b]:
                pair = (b, a)
                if pair not in seen:
                    seen.add(pair)
                    broken.append(pair)
    return broken


def find_dead_links(pages: list[WikiPage]) -> list[tuple[str, str]]:
    """A의 링크 대상이 pages에 없으면 (A, target)."""
    existing = {p.slug for p in pages}
    dead: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        for target in _targets(page):
            if target not in existing:
                pair = (page.slug, target)
                if pair not in seen:
                    seen.add(pair)
                    dead.append(pair)
    return dead


def find_orphans(pages: list[WikiPage]) -> list[str]:
    """들어오는 링크 0 & 나가는 링크 0인 완전 고립 slug."""
    existing = {p.slug for p in pages}
    has_outbound: set[str] = set()
    has_inbound: set[str] = set()
    for page in pages:
        targets = _targets(page)
        if targets:
            has_outbound.add(page.slug)
        for target in targets:
            if target in existing:
                has_inbound.add(target)
    return [
        p.slug
        for p in pages
        if p.slug not in has_outbound and p.slug not in has_inbound
    ]
