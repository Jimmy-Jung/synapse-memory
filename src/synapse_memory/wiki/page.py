"""WikiPage — 통합형 wiki 페이지 (yaml frontmatter + markdown body).

6개 타입(project/company/person/concept/profile/insight)을 단일 frozen
dataclass로 표현. cards/project.py 패턴을 일반화. 사람이 Obsidian에서 직접
편집 가능하고 Python에서도 parse/serialize 가능.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

FRONTMATTER_DELIMITER = "---"
VALID_TYPES: tuple[str, ...] = (
    "project",
    "company",
    "person",
    "concept",
    "profile",
    "insight",
)

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)


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
    updated: str = ""
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
    if page.updated:
        d["updated"] = page.updated
    d["status"] = page.status
    d["tags"] = ["node/wiki", f"node/{page.type}"]
    return d


def serialize_page(page: WikiPage) -> str:
    """WikiPage → markdown 문자열 (yaml frontmatter + body).

    body의 leading newline은 직렬화 시 제거(정규화)된다.
    """
    if page.type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page.type!r}")
    fm = _frontmatter_dict(page)
    yaml_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    body = page.body.lstrip("\n")
    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}"


def parse_page(text: str) -> WikiPage:
    """markdown 문자열 → WikiPage.

    Raises:
        ValueError: frontmatter 없음 / type 미지원 / slug·title 누락 / yaml 오류.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("frontmatter (--- ... ---) 없음")
    try:
        meta = yaml.safe_load(m.group("yaml")) or {}
    except (yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")

    page_type = meta.get("type")
    if page_type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    slug = meta.get("slug")
    title = meta.get("title")
    if not slug:
        raise ValueError("필수 필드 누락: slug")
    if not title:
        raise ValueError("필수 필드 누락: title")

    return WikiPage(
        type=str(page_type),
        slug=str(slug),
        title=str(title),
        related=tuple(str(x) for x in (meta.get("related") or [])),
        sources=tuple(str(x) for x in (meta.get("sources") or [])),
        updated=str(meta.get("updated") or ""),
        status=str(meta.get("status") or "active"),
        body=m.group("body"),
    )
