"""WikiPage — 통합형 wiki 페이지 (yaml frontmatter + markdown body).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from synapse_memory.config import get_vault_path
from synapse_memory.folders import year_month_path
from synapse_memory.model import (
    ENTITY_TYPES,
    folder_for,
    parse_frontmatter,
    serialize_frontmatter,
    uses_year_month_folder,
)

VALID_TYPES = ENTITY_TYPES

# slug에 허용하지 않는 문자(영숫자·한글 음절·하이픈 외)를 ``-``로 치환.
_SLUG_RE = re.compile(r"[^0-9a-z가-힣-]+")

# 본문 내 [[링크]] 위키링크 대상 추출.
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


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
        updated=updated_str,
        status=str(meta.get("status") or "active"),
        body=body,
    )


# ---------------------------------------------------------------------------
# slug + 디스크 I/O
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """display name → file-safe slug. 한국어 음절 보존, 공백 → ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def _type_base(page_type: str, vault_path: Path | None = None) -> Path:
    """타입별 schema 선언 루트."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / folder_for(page_type)


def page_dir(
    page_type: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> Path:
    """페이지 타입별 저장 디렉토리. schema의 year_month 타입은 연/월 하위폴더 사용."""
    if page_type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    base = _type_base(page_type, vault_path)
    if uses_year_month_folder(page_type):
        return year_month_path(base, when or date.today())
    return base


def _insight_when(page: WikiPage) -> date:
    """insight 페이지의 updated(YYYY-MM-DD)로 연/월 폴더 결정. 없으면 today."""
    if page.updated:
        try:
            return date.fromisoformat(page.updated)
        except ValueError:
            pass
    return date.today()


def page_path(page: WikiPage, *, vault_path: Path | None = None) -> Path:
    """페이지의 디스크 경로."""
    when = _insight_when(page) if uses_year_month_folder(page.type) else None
    return page_dir(page.type, vault_path=vault_path, when=when) / page.filename


def save_page(page: WikiPage, *, vault_path: Path | None = None) -> Path:
    """WikiPage → vault 디스크. 디렉토리 자동 생성. 기존 파일 덮어씀."""
    path = page_path(page, vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_page(page), encoding="utf-8")
    return path


def load_page(
    page_type: str,
    slug: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> WikiPage:
    """타입+slug로 페이지 로드.

    Raises:
        FileNotFoundError: 해당 페이지 없음.
    """
    if "/" in slug or "\\" in slug:
        raise ValueError(f"잘못된 slug (경로 구분자 포함): {slug!r}")
    path = page_dir(page_type, vault_path=vault_path, when=when) / f"{slug}.md"
    if not path.is_file():
        raise FileNotFoundError(f"wiki 페이지 없음: {path}")
    return parse_page(path.read_text(encoding="utf-8"))


def list_pages(
    page_type: str,
    *,
    vault_path: Path | None = None,
) -> list[WikiPage]:
    """해당 타입 모든 페이지 로드 (parse 실패는 skip). slug 알파벳순.

    schema의 year_month 타입은 연/월 하위폴더를 재귀 탐색한다.
    """
    if uses_year_month_folder(page_type):
        base = _type_base(page_type, vault_path)
    else:
        base = page_dir(page_type, vault_path=vault_path)
    if not base.is_dir():
        return []
    pages: list[WikiPage] = []
    for p in base.rglob("*.md"):
        try:
            pages.append(parse_page(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(pages, key=lambda pg: pg.slug)


# ---------------------------------------------------------------------------
# 링크 그래프 헬퍼
# ---------------------------------------------------------------------------


def extract_wikilinks(text: str) -> list[str]:
    """본문에서 [[링크]] 대상을 등장 순서로, 중복 제거해 반환."""
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.findall(text):
        target = match.split("|", 1)[0].strip()
        if target and target not in seen:
            seen[target] = None
    return list(seen.keys())


def with_related(page: WikiPage, link: str) -> WikiPage:
    """related에 link를 추가한 새 WikiPage 반환 (불변, target 기준 중복 무시).

    link는 "[[slug]]" 형식 권장. 이미 같은 대상(별칭 포함)을 링크하면 no-op.
    """
    new_targets = extract_wikilinks(link) or [link.strip("[]").strip()]
    new_target = new_targets[0] if new_targets else link
    for existing in page.related:
        existing_targets = extract_wikilinks(existing) or [existing.strip("[]").strip()]
        if new_target in existing_targets:
            return page
    return replace(page, related=(*page.related, link))
