"""WikiPage — 통합형 wiki 페이지 (yaml frontmatter + markdown body).

6개 타입(project/company/person/concept/profile/insight)을 단일 frozen
dataclass로 표현. cards/project.py 패턴을 일반화. 사람이 Obsidian에서 직접
편집 가능하고 Python에서도 parse/serialize 가능.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config
from synapse_memory.folders import year_month_path

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


# ---------------------------------------------------------------------------
# slug + 디스크 I/O
# ---------------------------------------------------------------------------

_TYPE_FOLDER_ATTR = {
    "project": "projects",
    "company": "companies",
    "person": "people",
    "concept": "concepts",
    "profile": "profile",
}


def slugify(name: str) -> str:
    """display name → file-safe slug. 한국어 음절 보존, 공백 → ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def _insight_base(vault_path: Path | None = None) -> Path:
    """Insights 루트 (연/월 하위폴더 없이)."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / get_config().vault_folders.wiki.insights


def page_dir(
    page_type: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> Path:
    """페이지 타입별 저장 디렉토리. insight는 연/월 하위폴더 사용."""
    if page_type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    if page_type == "insight":
        return year_month_path(_insight_base(vault_path), when or date.today())
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    sub = getattr(get_config().vault_folders.wiki, _TYPE_FOLDER_ATTR[page_type])
    return vault / sub


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
    when = _insight_when(page) if page.type == "insight" else None
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

    insight는 연/월 하위폴더를 재귀 탐색한다.
    """
    if page_type == "insight":
        base = _insight_base(vault_path)
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
        target = match.strip()
        if target and target not in seen:
            seen[target] = None
    return list(seen.keys())


def with_related(page: WikiPage, link: str) -> WikiPage:
    """related에 link를 추가한 새 WikiPage 반환 (불변, 중복 무시).

    link는 "[[slug]]" 형식을 권장.
    """
    if link in page.related:
        return page
    return replace(page, related=(*page.related, link))
