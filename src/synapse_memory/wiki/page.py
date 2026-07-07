"""Entity-backed page compatibility exports."""
from __future__ import annotations

import re

from synapse_memory.model import ENTITY_TYPES, Entity, parse_entity, serialize_entity
from synapse_memory.store import (
    list_pages,
    load_page,
    page_dir,
    page_path,
    save_page,
)
from synapse_memory.wiki.links import (
    extract_wikilinks,
    with_related,
)

VALID_TYPES = ENTITY_TYPES
WikiPage = Entity
parse_page = parse_entity
serialize_page = serialize_entity

_SLUG_RE = re.compile(r"[^0-9a-z가-힣-]+")

__all__ = [
    "VALID_TYPES",
    "WikiPage",
    "extract_wikilinks",
    "list_pages",
    "load_page",
    "page_dir",
    "page_path",
    "parse_page",
    "save_page",
    "serialize_page",
    "slugify",
    "with_related",
]


def slugify(name: str) -> str:
    """display name -> file-safe slug. 한국어 음절 보존, 공백 -> ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"
