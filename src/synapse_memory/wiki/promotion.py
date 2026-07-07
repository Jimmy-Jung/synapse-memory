"""반복 log 패턴 → insight 승격 후보 (CQ14).

저자: JunyoungJung
작성일: 2026-07-07

ponytail: 제목 정규화 그룹핑 휴리스틱 — 의미 유사 클러스터링은 후속.
"""
from __future__ import annotations

from collections.abc import Iterable

from synapse_memory.model import Entity
from synapse_memory.wiki.page import slugify

PROMOTION_SLUG_PREFIX = "promoted"


def promotion_candidates_from_logs(
    logs: Iterable[Entity],
    *,
    min_count: int = 2,
) -> list[Entity]:
    """같은 주제(정규화 제목)가 min_count회 이상 반복된 log를 insight 후보로.

    저장하지 않는다 — 후보 Entity만 반환(승격 여부는 호출자/사람이 결정).
    """
    grouped: dict[str, list[Entity]] = {}
    for log in logs:
        if log.type != "log":
            continue
        key = log.title.strip().lower()
        if key:
            grouped.setdefault(key, []).append(log)

    candidates: list[Entity] = []
    for group in grouped.values():
        if len(group) < min_count:
            continue
        first = group[0]
        slugs = [log.slug for log in group]
        body_lines = [
            f"반복 활동 패턴 ({len(group)}회): {first.title}",
            "",
            *(f"- [[{slug}]]" for slug in slugs),
            "",
            first.body,
        ]
        candidates.append(
            Entity(
                type="insight",
                slug=f"{PROMOTION_SLUG_PREFIX}-{slugify(first.title)}",
                title=f"{first.title} — 반복 패턴 승격 후보",
                body="\n".join(body_lines),
                decided_in=tuple(slugs),
                sources=("promotion",),
                status="draft",
            )
        )
    return candidates
