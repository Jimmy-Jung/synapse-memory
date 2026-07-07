"""WikiPage — 통합형 wiki 페이지 (yaml frontmatter + markdown body).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from synapse_memory.model import (
    ENTITY_TYPES,
    parse_frontmatter,
    serialize_frontmatter,
)
from synapse_memory.model.entity import OBSERVED_AT_TYPES, RELATION_FIELDS
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

# slug에 허용하지 않는 문자(영숫자·한글 음절·하이픈 외)를 ``-``로 치환.
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


@dataclass(frozen=True)
class WikiPage:
    """LLM이 소유·유지하는 단일 지식 페이지.

    불변(frozen). 갱신은 dataclasses.replace 또는 with_related로 새 객체 생성.
    """

    type: str
    slug: str
    title: str
    related: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()
    part_of: tuple[str, ...] = ()
    about: tuple[str, ...] = ()
    decided_in: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    same_as: tuple[str, ...] = ()
    created: str = ""
    updated: str = ""
    observed_at: str = ""
    status: str = "active"
    body: str = ""

    @property
    def filename(self) -> str:
        return f"{self.slug}.md"


def _frontmatter_dict(page: WikiPage) -> dict[str, Any]:
    """body 제외 필드를 dict로. 빈 컬렉션은 생략 — 깔끔한 yaml."""
    d: dict[str, Any] = {
        "type": page.type,
        "slug": page.slug,
        "title": page.title,
    }
    if page.related:
        d["related"] = list(page.related)
    if page.sources:
        d["sources"] = list(page.sources)
    for key in RELATION_FIELDS:
        values = tuple(getattr(page, key) or ())
        if values:
            d[key] = list(values)
    if page.created:
        d["created"] = page.created
    if page.updated:
        d["updated"] = page.updated
    if page.type in OBSERVED_AT_TYPES and page.observed_at:
        d["observed_at"] = page.observed_at
    d["status"] = page.status
    return d


def serialize_page(page: WikiPage) -> str:
    """WikiPage → markdown 문자열 (yaml frontmatter + body).

    body의 leading newline은 직렬화 시 제거(정규화)된다.
    """
    if page.type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page.type!r}")
    fm = _frontmatter_dict(page)
    return serialize_frontmatter(fm, page.body)


def parse_page(text: str) -> WikiPage:
    """markdown 문자열 → WikiPage.

    Raises:
        ValueError: frontmatter 없음 / type 미지원 / slug·title 누락 / yaml 오류.
    """
    try:
        meta, body = parse_frontmatter(text)
    except ValueError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc

    page_type = meta.get("type")
    if page_type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    slug = meta.get("slug")
    title = meta.get("title")
    if not slug:
        raise ValueError("필수 필드 누락: slug")
    if not title:
        raise ValueError("필수 필드 누락: title")

    updated_str = str(meta.get("updated") or "")
    if updated_str:
        try:
            date.fromisoformat(updated_str)
        except ValueError as exc:
            raise ValueError(f"updated 형식 오류 (YYYY-MM-DD 필요): {updated_str!r}") from exc

    return WikiPage(
        type=str(page_type),
        slug=str(slug),
        title=str(title),
        related=tuple(str(x) for x in (meta.get("related") or [])),
        sources=tuple(str(x) for x in (meta.get("sources") or [])),
        **{
            key: tuple(str(x) for x in (meta.get(key) or []))
            for key in RELATION_FIELDS
        },
        created=str(meta.get("created") or ""),
        updated=updated_str,
        observed_at=(
            str(meta.get("observed_at") or "")
            if page_type in OBSERVED_AT_TYPES
            else ""
        ),
        status=str(meta.get("status") or "active"),
        body=body,
    )


def slugify(name: str) -> str:
    """display name → file-safe slug. 한국어 음절 보존, 공백 → ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"
