"""Entity index for provider-only retrieval.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from dataclasses import dataclass

from synapse_memory.model import Entity

DEFAULT_SUMMARY_CHARS = 200


@dataclass(frozen=True)
class PageEntry:
    """인덱스 한 줄 — provider가 관련성 판단에 쓰는 최소 정보."""

    slug: str
    title: str
    summary: str


@dataclass(frozen=True)
class PageIndex:
    """프롬프트에 통째로 들어가는 페이지 인덱스."""

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
    pages: list[Entity], *, summary_chars: int = DEFAULT_SUMMARY_CHARS
) -> PageIndex:
    """Entity 목록 → PageIndex. slug 정렬로 결정적 출력."""
    entries = tuple(
        PageEntry(
            slug=p.slug,
            title=p.title,
            summary=_summarize(p.body, max_chars=summary_chars),
        )
        for p in sorted(pages, key=lambda p: p.slug)
    )
    return PageIndex(entries=entries)
