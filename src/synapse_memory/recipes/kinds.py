"""Shared source-kind mappings for recipe and endpoint adapters.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from typing import Literal

CardKind = Literal["project", "company", "insight"]

SOURCE_KIND_TO_CARD_KIND: dict[str, CardKind] = {
    "card_project": "project",
    "card_company": "company",
    "card_insight": "insight",
}
_SOURCE_KIND_TO_CARD_KIND = SOURCE_KIND_TO_CARD_KIND


def card_kind_for_source_kind(source_kind: str) -> CardKind | None:
    return SOURCE_KIND_TO_CARD_KIND.get(source_kind)


def is_known_source_kind(value: object) -> bool:
    return isinstance(value, str) and value in SOURCE_KIND_TO_CARD_KIND
