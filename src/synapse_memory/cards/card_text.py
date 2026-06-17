# src/synapse_memory/cards/card_text.py
"""Card → 검색/프롬프트용 단일 텍스트 변환 (020 provider-only).

이전에는 ``rag/indexer.py`` 가 임베딩 대상 텍스트를 만들었으나, 로컬 ML 제거 후
provider 선별 → 선택 카드 full text 합성 경로에서 동일 변환이 필요해 여기로 이전했다.
임베딩/벡터 의존 없음 — 순수 문자열 변환만 담당한다.

저자: Synapse Memory Maintainers
작성일: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

from synapse_memory.cards.company import CompanyCard
from synapse_memory.cards.insight import InsightCard
from synapse_memory.cards.project import ProjectCard


def _join_strings(values: Sequence[object]) -> str:
    return ", ".join(str(value) for value in values)


def project_card_to_text(card: ProjectCard) -> str:
    """ProjectCard → 단일 텍스트 (yaml 메타 + body 통합)."""
    lines: list[str] = [f"# {card.display_name}"]
    if card.role:
        lines.append(f"역할: {card.role}")
    period = card.period_start or ""
    if card.period_end:
        period = f"{period} ~ {card.period_end}".strip(" ~")
    if period:
        lines.append(f"기간: {period}")
    if card.status:
        lines.append(f"상태: {card.status}")
    if card.domains:
        lines.append(f"도메인: {_join_strings(card.domains)}")
    if card.stack:
        lines.append(f"기술 스택: {_join_strings(card.stack)}")
    if card.keywords:
        lines.append(f"키워드: {_join_strings(card.keywords)}")
    if card.metrics:
        lines.append("지표:")
        for m in card.metrics:
            if m.value:
                lines.append(f"  - {m.name}: {m.value}")
            elif m.before or m.after:
                lines.append(f"  - {m.name}: {m.before or ''} → {m.after or ''}")
    if card.body:
        lines.append("")
        lines.append(card.body.strip())
    return "\n".join(lines)


def company_card_to_text(card: CompanyCard) -> str:
    """CompanyCard → 단일 텍스트."""
    lines: list[str] = [f"# {card.display_name}"]
    if card.country:
        lines.append(f"국가: {card.country}")
    if card.size:
        lines.append(f"규모: {card.size}")
    if card.status:
        lines.append(f"상태: {card.status}")
    if card.website:
        lines.append(f"웹사이트: {card.website}")
    if card.positions:
        lines.append("포지션:")
        for p in card.positions:
            extras: list[str] = []
            if p.seniority:
                extras.append(p.seniority)
            if p.keywords:
                extras.append(_join_strings(p.keywords))
            extras_str = f" ({'; '.join(extras)})" if extras else ""
            lines.append(f"  - {p.title}{extras_str}")
    if card.body:
        lines.append("")
        lines.append(card.body.strip())
    return "\n".join(lines)


def insight_card_to_text(card: InsightCard) -> str:
    """InsightCard → 단일 텍스트."""
    lines: list[str] = [
        f"# {card.question}",
        f"명령: {card.command}",
        f"상태: {card.status}",
    ]
    if card.related:
        lines.append(f"관련 카드: {_join_strings(card.related)}")
    if card.keywords:
        lines.append(f"키워드: {_join_strings(card.keywords)}")
    if card.body:
        lines.append("")
        lines.append(card.body.strip())
    return "\n".join(lines)
