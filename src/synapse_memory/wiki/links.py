"""Wiki forward-link helpers.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TypeVar, cast

from synapse_memory.model.entity import RELATION_FIELDS

PageT = TypeVar("PageT")

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(text: str) -> list[str]:
    """본문에서 [[링크]] 대상을 등장 순서로, 중복 제거해 반환."""
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.findall(text):
        target = match.split("|", 1)[0].strip()
        if target and target not in seen:
            seen[target] = None
    return list(seen.keys())


def link_target(link: str) -> str:
    """단일 related 링크 문자열에서 slug 대상을 추출."""
    extracted = extract_wikilinks(link) or [link.strip("[]").strip()]
    return extracted[0] if extracted else ""


def with_related(page: PageT, link: str) -> PageT:
    """related에 link를 추가한 새 page 반환. 대상 slug 기준 중복은 no-op."""
    new_target = link_target(link)
    for existing in getattr(page, "related", ()):
        if new_target == link_target(existing):
            return page
    related = tuple(getattr(page, "related", ()))
    return cast(PageT, replace(page, related=(*related, link)))


def typed_neighbors(page: object) -> dict[str, tuple[str, ...]]:
    """Typed relation neighbors grouped by relation name."""
    grouped: dict[str, tuple[str, ...]] = {}
    for relation in RELATION_FIELDS:
        targets = _relation_targets(getattr(page, relation, ()))
        if targets:
            grouped[relation] = targets
    return grouped


def reverse_relations(pages: list[object]) -> dict[str, list[tuple[str, str]]]:
    """Index typed incoming edges as target slug -> [(relation, source slug)]."""
    index: dict[str, list[tuple[str, str]]] = {}
    for page in pages:
        source = str(getattr(page, "slug", "") or "")
        if not source:
            continue
        for relation, targets in typed_neighbors(page).items():
            for target in targets:
                index.setdefault(target, []).append((relation, source))
    return index


def neighbor_links(page: object) -> tuple[str, ...]:
    """1-hop 확장용 링크: legacy related와 typed relation을 합친다."""
    links: list[str] = []
    for targets in typed_neighbors(page).values():
        links.extend(targets)
    links.extend(link_target(str(link)) for link in getattr(page, "related", ()))
    return tuple(links)


def _relation_targets(values: object) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    raw_values = (values,) if isinstance(values, str) else tuple(values or ())
    for value in raw_values:
        target = link_target(str(value))
        if target and target not in seen:
            seen[target] = None
    return tuple(seen)
