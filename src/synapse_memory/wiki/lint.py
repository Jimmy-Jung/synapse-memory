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

from synapse_memory.retrieval.pages import _all_pages
from synapse_memory.store import save_page
from synapse_memory.wiki.links import link_target
from synapse_memory.wiki.log import append_log
from synapse_memory.wiki.page import WikiPage


def _targets(page: WikiPage) -> list[str]:
    """page.related의 각 링크에서 slug 대상을 추출 (등장순, 중복 제거)."""
    seen: dict[str, None] = {}
    for link in page.related:
        target = link_target(link)
        if target and target not in seen:
            seen[target] = None
    return list(seen.keys())


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

    dead_links_removed: int = 0


def apply_structural_fixes(*, vault_path: Path | None = None) -> LintReport:
    """죽은 forward 링크 제거. 멱등."""
    report = LintReport()

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
            link for link in source_page.related if link_target(link) not in bad
        )
        removed = len(source_page.related) - len(kept)
        if removed:
            save_page(dataclasses.replace(source_page, related=kept), vault_path=vault_path)
            report.dead_links_removed += removed

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
        f"lint: -{report.dead_links_removed} dead",
    )
    return report
