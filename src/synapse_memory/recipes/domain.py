"""Domain precedence resolver.

Spec: ``specs/007-me-recipes/spec.md`` FR-006.

precedence:
  1. CLI --domain arg
  2. Profile.md frontmatter `domain`
  3. matched ProjectCards 의 tag frequency ≥ 0.3
  4. default "generic"

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from synapse_memory.recipes.recipe import DomainSource

DEFAULT_DOMAIN = "generic"
TAG_FREQUENCY_THRESHOLD = 0.3

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n", re.DOTALL | re.MULTILINE
)
_FIELD_RE = re.compile(
    r"^\s*domain\s*:\s*(?P<v>['\"]?)(?P<value>[^\"'\n]+)(?P=v)\s*$",
    re.MULTILINE,
)


def _parse_profile_domain(profile_text: str) -> str | None:
    if not profile_text:
        return None
    m = _FRONTMATTER_RE.search(profile_text)
    if not m:
        return None
    field = _FIELD_RE.search(m.group("yaml"))
    if not field:
        return None
    val = field.group("value").strip()
    return val or None


def _collect_tags(matched: list[tuple[Any, float]]) -> list[str]:
    tags: list[str] = []
    for rec, _dist in matched:
        meta = getattr(rec, "metadata", None) or {}
        raw = meta.get("tags") if isinstance(meta, dict) else None
        if isinstance(raw, list):
            tags.extend(str(t) for t in raw if isinstance(t, str))
        elif isinstance(raw, str) and raw:
            tags.extend(t.strip() for t in raw.split(",") if t.strip())
    return tags


def resolve_domain(
    *,
    cli_arg: str | None = None,
    profile_text: str = "",
    matched: list[tuple[Any, float]] | None = None,
) -> tuple[str, DomainSource]:
    """precedence 에 따라 (domain, source) 결정."""
    if cli_arg and cli_arg.strip():
        return cli_arg.strip(), "cli"

    profile_dom = _parse_profile_domain(profile_text)
    if profile_dom:
        return profile_dom, "profile"

    matched = matched or []
    if matched:
        tags = _collect_tags(matched)
        if tags:
            counter = Counter(tags)
            top_tag, top_count = counter.most_common(1)[0]
            n_records = len(matched)
            if n_records > 0 and (top_count / n_records) >= TAG_FREQUENCY_THRESHOLD:
                return top_tag, "tags"

    return DEFAULT_DOMAIN, "default"
