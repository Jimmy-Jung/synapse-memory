"""wiki lint — 구조 자동 수정 + 사람 검토 큐 (전부 순수 Python, LLM 불필요).

R3 원칙: "구조는 자동, 진실은 사람".
- 구조 결함(끊긴 역링크, 죽은 링크, 고아)은 자동 수정.
- 진위 판단이 필요한 것(낡음 의심, 병합 후보)은 index.md 검토 큐에 나열만.

분석기(find_*)는 list[WikiPage] 입력의 순수 함수 — 결정적, 디스크 불필요.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

import dataclasses
import difflib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from synapse_memory.wiki.page import (
    VALID_TYPES,
    WikiPage,
    extract_wikilinks,
    list_pages,
    save_page,
    with_related,
)


def _targets(page: WikiPage) -> list[str]:
    """page.related의 각 링크에서 slug 대상을 추출 (등장순, 중복 제거)."""
    seen: dict[str, None] = {}
    for link in page.related:
        extracted = extract_wikilinks(link) or [link.strip("[]").strip()]
        for target in extracted:
            if target and target not in seen:
                seen[target] = None
    return list(seen.keys())


def _link_target(link: str) -> str:
    """단일 related 링크 문자열에서 slug 대상 추출."""
    extracted = extract_wikilinks(link) or [link.strip("[]").strip()]
    return extracted[0] if extracted else ""


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


# ---------------------------------------------------------------------------
# 구조 자동 수정
# ---------------------------------------------------------------------------


@dataclass
class LintReport:
    """lint 1회 실행 결과 요약."""

    backlinks_added: int = 0
    dead_links_removed: int = 0
    orphans: list[str] = field(default_factory=list)
    review_items: list[dict] = field(default_factory=list)


def _all_pages(*, vault_path: Path | None = None) -> list[WikiPage]:
    """전 타입 페이지 수집 (slug 알파벳순 — list_pages 보장)."""
    pages: list[WikiPage] = []
    for page_type in VALID_TYPES:
        pages.extend(list_pages(page_type, vault_path=vault_path))
    return pages


def apply_structural_fixes(*, vault_path: Path | None = None) -> LintReport:
    """죽은 링크 제거 + 누락 역링크 보강. 멱등.

    순서: ① 죽은 링크 먼저 제거(곧 삭제할 링크의 역링크를 만들지 않도록),
    ② 그 다음 누락 역링크 보강.
    """
    report = LintReport()

    # ① 죽은 링크 제거
    pages = _all_pages(vault_path=vault_path)
    dead = set(find_dead_links(pages))
    dead_targets_by_slug: dict[str, set[str]] = {}
    for src, target in dead:
        dead_targets_by_slug.setdefault(src, set()).add(target)
    for page in pages:
        bad = dead_targets_by_slug.get(page.slug)
        if not bad:
            continue
        kept = tuple(
            link for link in page.related if _link_target(link) not in bad
        )
        removed = len(page.related) - len(kept)
        if removed:
            save_page(dataclasses.replace(page, related=kept), vault_path=vault_path)
            report.dead_links_removed += removed

    # ② 누락 역링크 보강 (죽은 링크 제거 후 재수집)
    pages = _all_pages(vault_path=vault_path)
    by_slug = {p.slug: p for p in pages}
    broken = find_broken_backlinks(pages)
    for needs_backlink, link_to in broken:
        page = by_slug.get(needs_backlink)
        if page is None:
            continue
        updated = with_related(page, f"[[{link_to}]]")
        if updated is not page and updated.related != page.related:
            save_page(updated, vault_path=vault_path)
            by_slug[needs_backlink] = updated
            report.backlinks_added += 1

    return report


# ---------------------------------------------------------------------------
# 검토 큐 휴리스틱 (자동 수정 안 함 — index.md에 나열만)
# ---------------------------------------------------------------------------


def stale_candidates(
    pages: list[WikiPage],
    *,
    today: str | None = None,
    max_age_days: int = 180,
) -> list[str]:
    """낡음 의심 페이지 slug. type=="insight"는 skip.

    updated 없으면 flag; 있으면 updated < today - max_age_days면 flag.
    today 미지정 → 오늘.
    """
    today_date = date.fromisoformat(today) if today else date.today()
    cutoff = today_date - timedelta(days=max_age_days)
    flagged: list[str] = []
    for page in pages:
        if page.type == "insight":
            continue
        if not page.updated:
            flagged.append(page.slug)
            continue
        try:
            updated_date = date.fromisoformat(page.updated)
        except ValueError:
            flagged.append(page.slug)
            continue
        if updated_date < cutoff:
            flagged.append(page.slug)
    return flagged


def merge_candidates(
    pages: list[WikiPage],
    *,
    threshold: float = 0.9,
) -> list[tuple[str, str]]:
    """같은 type 페이지쌍 중 제목 유사도 >= threshold인 (slug1, slug2)."""
    pairs: list[tuple[str, str]] = []
    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            p1, p2 = pages[i], pages[j]
            if p1.type != p2.type:
                continue
            ratio = difflib.SequenceMatcher(
                None, p1.title.lower(), p2.title.lower()
            ).ratio()
            if ratio >= threshold:
                pairs.append((p1.slug, p2.slug))
    return pairs
