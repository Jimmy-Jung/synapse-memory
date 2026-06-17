# src/synapse_memory/wiki/page_index.py
"""PageIndex — LLM-as-retriever용 경량 wiki 페이지 인덱스 (020).

로컬 임베딩(bge-m3) 제거 후, 관련 페이지 선별/검색을 provider LLM에 맡기기 위한
프롬프트 친화적 인덱스. slug/title/요약만 담아 토큰을 아낀다.

저자: Synapse Memory Maintainers
작성일: 2026-06-16
"""
from __future__ import annotations

from dataclasses import dataclass

from synapse_memory.wiki.page import WikiPage

# 요약은 본문 첫 N자 (별도 summary 필드 없음). 프롬프트 토큰 절약 + 의미 판단 보강.
DEFAULT_SUMMARY_CHARS = 200


@dataclass(frozen=True)
class PageEntry:
    """인덱스 한 줄 — provider가 관련성 판단에 쓰는 최소 정보."""

    slug: str
    title: str
    summary: str


@dataclass(frozen=True)
class PageIndex:
    """프롬프트에 통째로 들어가는 페이지 인덱스. 수십~수백 페이지 규모 가정."""

    entries: tuple[PageEntry, ...]

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def slugs(self) -> frozenset[str]:
        return frozenset(e.slug for e in self.entries)

    def render(self) -> str:
        """프롬프트용 라인 — ``[slug] title — summary``."""
        return "\n".join(
            f"[{e.slug}] {e.title} — {e.summary}"
            if e.summary
            else f"[{e.slug}] {e.title}"
            for e in self.entries
        )


def _summarize(body: str, *, max_chars: int) -> str:
    """본문 첫 max_chars자 1줄 요약(개행→공백 압축)."""
    flat = " ".join(body.split())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rstrip() + "…"


def build_page_index(
    pages: list[WikiPage], *, summary_chars: int = DEFAULT_SUMMARY_CHARS
) -> PageIndex:
    """WikiPage 목록 → PageIndex. slug 정렬로 결정적 출력."""
    entries = tuple(
        PageEntry(
            slug=p.slug,
            title=p.title,
            summary=_summarize(p.body, max_chars=summary_chars),
        )
        for p in sorted(pages, key=lambda p: p.slug)
    )
    return PageIndex(entries=entries)
