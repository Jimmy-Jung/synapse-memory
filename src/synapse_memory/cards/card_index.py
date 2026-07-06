# src/synapse_memory/cards/card_index.py
"""CardIndex — provider-only 카드 검색용 경량 인덱스 (020 Stage 1).

로컬 임베딩/벡터스토어를 provider LLM-as-retriever로 대체하기 위한 토대.
Project/Company/Insight 카드를 열거해 id/title/summary + 타임라인 메타를 담는다.
``retrieval.index.select_related``와 호환되도록 ``entries``/``render()``/``slugs``를
노출 — 같은 provider 선별 헬퍼를 카드에도 재사용한다.

저자: Synapse Memory Maintainers
작성일: 2026-06-17
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from synapse_memory.cards.company import list_company_cards
from synapse_memory.cards.insight import list_insight_cards
from synapse_memory.cards.project import list_project_cards

CardKind = Literal["project", "company", "insight"]

DEFAULT_SUMMARY_CHARS = 240


@dataclass(frozen=True)
class CardEntry:
    """인덱스 한 줄 — provider 선별 + 타임라인 정렬에 필요한 최소 정보."""

    card_id: str
    kind: CardKind
    title: str
    summary: str
    meta: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CardIndex:
    """프롬프트에 통째로 들어가는 카드 인덱스. select_related 호환.

    ``slugs``/``entries``/``render()``를 노출하므로
    ``retrieval.index.select_related(query, card_index, ...)``를 그대로 쓸 수 있다.
    """

    entries: tuple[CardEntry, ...]

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def slugs(self) -> frozenset[str]:
        """select_related 호환 — 유효 식별자 집합(여기선 card_id)."""
        return frozenset(e.card_id for e in self.entries)

    def by_id(self) -> dict[str, CardEntry]:
        return {e.card_id: e for e in self.entries}

    def render(self) -> str:
        """프롬프트용 라인 — ``[card_id] (kind) title — summary``."""
        lines = []
        for e in self.entries:
            head = f"[{e.card_id}] ({e.kind}) {e.title}"
            lines.append(f"{head} — {e.summary}" if e.summary else head)
        return "\n".join(lines)


def _summarize(text: str, *, max_chars: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rstrip() + "…"


def build_card_index(
    *,
    vault_path: Path | None = None,
    kinds: tuple[CardKind, ...] = ("project", "company", "insight"),
    summary_chars: int = DEFAULT_SUMMARY_CHARS,
) -> CardIndex:
    """vault의 카드를 열거해 CardIndex 생성. card_id 정렬로 결정적 출력.

    임베딩 없음 — 카드 파일만 읽는다. 타임라인 정렬용 메타(period_end/status/
    created/last_reviewed/display_name/source_kind)를 ``meta``에 담는다.
    """
    entries: list[CardEntry] = []

    if "project" in kinds:
        for project in list_project_cards(vault_path=vault_path):
            entries.append(
                CardEntry(
                    card_id=project.project_id,
                    kind="project",
                    title=project.display_name,
                    summary=_summarize(project.body, max_chars=summary_chars),
                    meta={
                        "source_kind": "card_project",
                        "display_name": project.display_name,
                        "status": project.status,
                        "period_end": project.period_end or "",
                        "created": project.created,
                        "last_reviewed": project.last_reviewed,
                    },
                )
            )

    if "company" in kinds:
        for company in list_company_cards(vault_path=vault_path):
            entries.append(
                CardEntry(
                    card_id=company.company_id,
                    kind="company",
                    title=company.display_name,
                    summary=_summarize(company.body or company.notes, max_chars=summary_chars),
                    meta={
                        "source_kind": "card_company",
                        "display_name": company.display_name,
                        "status": company.status,
                        "created": company.created,
                        "last_reviewed": company.last_reviewed,
                    },
                )
            )

    if "insight" in kinds:
        for insight in list_insight_cards(vault_path=vault_path):
            entries.append(
                CardEntry(
                    card_id=insight.insight_id,
                    kind="insight",
                    title=insight.question,
                    summary=_summarize(insight.body, max_chars=summary_chars),
                    meta={
                        "source_kind": "card_insight",
                        "display_name": insight.question,
                        "created": insight.created,
                    },
                )
            )

    entries.sort(key=lambda e: e.card_id)
    return CardIndex(entries=tuple(entries))
