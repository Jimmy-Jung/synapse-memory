"""Company entity compatibility helpers.

이력서 작성 시:
    - 회사별 매칭 키워드, 포지션 정보
    - 사용자가 누적한 회사 메모 (web 검색, 면접 후기 등)
    - Project Card와 매칭되어 회사별 맞춤 이력서 생성

저장 위치: ``<vault>/Entities/Companies/<company_id>.md``

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from synapse_memory.cards.project import ProjectSource
from synapse_memory.config import get_config, get_vault_path
from synapse_memory.model import Entity, attr_dict, parse_frontmatter, serialize_entity

DEFAULT_COMPANIES_SUBPATH = Path("Entities") / "Companies"

VALID_STATUSES = (
    "target", "applied", "interviewing", "offered", "rejected", "hired", "superseded"
)
VALID_SIZES = ("startup", "small", "medium", "large", "mega")


COMPANY_DEFAULT_ATTRS: dict[str, Any] = {
    "country": None,
    "size": None,
    "website": None,
    "resume_language": None,
    "positions": [],
    "notes": "",
    "confidence": 1.0,
    "last_reviewed": "",
}


def JobPosition(
    title: str,
    seniority: str | None = None,
    keywords: list[str] | None = None,
    jd_url: str | None = None,
) -> Any:
    """Company position attr value."""
    return attr_dict(
        title=title,
        seniority=seniority,
        keywords=list(keywords or []),
        jd_url=jd_url,
    )


def CompanyCard(
    company_id: str,
    display_name: str,
    status: str = "target",
    country: str | None = None,
    size: str | None = None,
    website: str | None = None,
    positions: list[Any] | None = None,
    notes: str = "",
    sources: list[Any] | None = None,
    confidence: float = 1.0,
    created: str | None = None,
    last_reviewed: str = "",
    supersedes: list[str] | None = None,
    body: str = "",
    resume_language: str | None = None,
) -> Entity:
    """Compatibility constructor returning the single Entity model."""
    attrs = _company_attrs(
        country=country,
        size=size,
        website=website,
        resume_language=resume_language,
        positions=list(positions or []),
        notes=notes,
        confidence=confidence,
        last_reviewed=last_reviewed,
    )
    return Entity(
        slug=company_id,
        title=display_name,
        type="company",
        status=status,
        created=created,
        sources=tuple(sources or ()),
        body=body,
        attrs=attrs,
        supersedes=tuple(supersedes or ()),
    )


def serialize_company_card(card: Entity) -> str:
    return serialize_entity(card)


def parse_company_card(text: str) -> Entity:
    meta, body = parse_frontmatter(text)
    if "type" not in meta:
        meta = {
            **meta,
            "type": "company",
            "slug": meta.get("company_id"),
            "title": meta.get("display_name"),
        }
    if meta.get("type") != "company":
        raise ValueError(f"알 수 없는 company type: {meta.get('type')!r}")
    company_id = meta.get("slug")
    display_name = meta.get("title")
    if not company_id or not display_name:
        raise ValueError("필수 필드 누락: company_id, display_name")

    positions = [
        JobPosition(
            title=p["title"],
            seniority=p.get("seniority"),
            keywords=list(p.get("keywords") or []),
            jd_url=p.get("jd_url"),
        )
        for p in meta.get("positions", []) or []
        if isinstance(p, dict) and "title" in p
    ]
    sources = [
        ProjectSource(type=s["type"], path=s["path"])
        for s in meta.get("sources", []) or []
        if isinstance(s, dict) and "type" in s and "path" in s
    ]

    return CompanyCard(
        company_id=str(company_id),
        display_name=str(display_name),
        status=str(meta.get("status", "target")),
        country=meta.get("country"),
        size=meta.get("size"),
        website=meta.get("website"),
        positions=positions,
        notes=str(meta.get("notes", "")),
        sources=sources,
        confidence=float(meta.get("confidence", 1.0)),
        created=str(meta.get("created", "")),
        last_reviewed=str(meta.get("last_reviewed", "")),
        supersedes=_relation_list(meta.get("supersedes")),
        body=body,
        resume_language=meta.get("resume_language"),
    )


def companies_dir(vault_path: Path | None = None) -> Path:
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / get_config().vault_folders.wiki.companies


def load_company_card(
    company_id: str, *, vault_path: Path | None = None
) -> Entity:
    path = companies_dir(vault_path) / f"{company_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Company Card 없음: {path}")
    return parse_company_card(path.read_text(encoding="utf-8"))


def save_company_card(
    card: Entity, *, vault_path: Path | None = None
) -> Path:
    path = companies_dir(vault_path) / card.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_company_card(card), encoding="utf-8")
    return path


def list_company_cards(
    *, vault_path: Path | None = None
) -> list[Entity]:
    d = companies_dir(vault_path)
    if not d.is_dir():
        return []
    cards: list[Entity] = []
    for p in sorted(d.glob("*.md")):
        try:
            cards.append(parse_company_card(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(cards, key=lambda c: c.company_id)


def _company_attrs(**values: Any) -> dict[str, Any]:
    return {**COMPANY_DEFAULT_ATTRS, **values}


def _relation_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
