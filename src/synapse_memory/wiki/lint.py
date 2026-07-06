"""wiki lint — 구조 자동 수정 (전부 순수 Python, LLM 불필요).

R3 원칙: "구조는 자동, 진실은 사람".
- 구조 결함(끊긴 역링크, 죽은 링크)은 자동 수정.

분석기(find_*)는 list[WikiPage] 입력의 순수 함수 — 결정적, 디스크 불필요.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.wiki.log import append_log
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


# ---------------------------------------------------------------------------
# 구조 자동 수정
# ---------------------------------------------------------------------------


@dataclass
class LintReport:
    """lint 1회 실행 결과 요약."""

    backlinks_added: int = 0
    dead_links_removed: int = 0


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
    for source_page in pages:
        bad = dead_targets_by_slug.get(source_page.slug)
        if not bad:
            continue
        kept = tuple(
            link for link in source_page.related if _link_target(link) not in bad
        )
        removed = len(source_page.related) - len(kept)
        if removed:
            save_page(dataclasses.replace(source_page, related=kept), vault_path=vault_path)
            report.dead_links_removed += removed

    # ② 누락 역링크 보강 (죽은 링크 제거 후 재수집)
    # redesign: Step 6 재검토
    pages = _all_pages(vault_path=vault_path)
    by_slug = {p.slug: p for p in pages}
    broken = find_broken_backlinks(pages)
    for needs_backlink, link_to in broken:
        target_page = by_slug.get(needs_backlink)
        if target_page is None:
            continue
        updated = with_related(target_page, f"[[{link_to}]]")
        if updated is not target_page and updated.related != target_page.related:
            save_page(updated, vault_path=vault_path)
            by_slug[needs_backlink] = updated
            report.backlinks_added += 1

    return report


# ---------------------------------------------------------------------------
# 전체 lint 오케스트레이션
# ---------------------------------------------------------------------------


def run_lint(
    *,
    vault_path: Path | None = None,
    today: str | None = None,
) -> LintReport:
    """구조 자동 수정 → log 기록."""
    _ = today
    report = apply_structural_fixes(vault_path=vault_path)

    append_log(
        f"lint: +{report.backlinks_added} backlinks, "
        f"-{report.dead_links_removed} dead",
    )
    return report
