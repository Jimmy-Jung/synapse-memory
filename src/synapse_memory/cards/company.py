"""Company Card — 지원/관심 회사의 진실원본.

이력서 작성 시:
    - 회사별 매칭 키워드, 포지션 정보
    - 사용자가 누적한 회사 메모 (web 검색, 면접 후기 등)
    - Project Card와 매칭되어 회사별 맞춤 이력서 생성

저장 위치: ``<vault>/20_Reference/Companies/<company_id>.md``

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from synapse_memory.cards.project import (
    FRONTMATTER_DELIMITER,
    ProjectSource,
    _FRONTMATTER_RE,
)
from synapse_memory.collectors.obsidian.mirror import get_vault_path

DEFAULT_COMPANIES_SUBPATH = Path("20_Reference") / "Companies"

VALID_STATUSES = (
    "target", "applied", "interviewing", "offered", "rejected", "hired"
)
VALID_SIZES = ("startup", "small", "medium", "large", "mega")


@dataclass
class JobPosition:
    """관심/지원 포지션."""

    title: str
    seniority: str | None = None  # junior | mid | senior | lead | principal
    keywords: list[str] = field(default_factory=list)
    jd_url: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"title": self.title}
        if self.seniority:
            d["seniority"] = self.seniority
        if self.keywords:
            d["keywords"] = self.keywords
        if self.jd_url:
            d["jd_url"] = self.jd_url
        return d


@dataclass
class CompanyCard:
    """회사 단위 진실원본."""

    company_id: str
    display_name: str
    status: str = "target"
    country: str | None = None
    size: str | None = None
    website: str | None = None
    positions: list[JobPosition] = field(default_factory=list)
    notes: str = ""
    sources: list[ProjectSource] = field(default_factory=list)
    confidence: float = 1.0
    created: str = ""
    last_reviewed: str = ""
    body: str = ""
    resume_language: str | None = None

    @property
    def filename(self) -> str:
        return f"{self.company_id}.md"


def _frontmatter_dict(card: CompanyCard) -> dict:
    d: dict = {
        "company_id": card.company_id,
        "display_name": card.display_name,
        "status": card.status,
    }
    for k, v in {
        "country": card.country,
        "size": card.size,
        "website": card.website,
        "resume_language": card.resume_language,
    }.items():
        if v:
            d[k] = v
    if card.positions:
        d["positions"] = [p.to_dict() for p in card.positions]
    if card.notes:
        d["notes"] = card.notes
    if card.sources:
        d["sources"] = [s.to_dict() for s in card.sources]
    d["confidence"] = card.confidence
    if card.created:
        d["created"] = card.created
    if card.last_reviewed:
        d["last_reviewed"] = card.last_reviewed
    return d


def serialize_company_card(card: CompanyCard) -> str:
    fm = _frontmatter_dict(card)
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip()
    body = card.body.lstrip("\n")
    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}"


def parse_company_card(text: str) -> CompanyCard:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("frontmatter (--- ... ---) 없음")

    try:
        meta = yaml.safe_load(m.group("yaml")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")

    company_id = meta.get("company_id")
    display_name = meta.get("display_name")
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
        body=m.group("body"),
        resume_language=meta.get("resume_language"),
    )


def companies_dir(vault_path: Path | None = None) -> Path:
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / DEFAULT_COMPANIES_SUBPATH


def load_company_card(
    company_id: str, *, vault_path: Path | None = None
) -> CompanyCard:
    path = companies_dir(vault_path) / f"{company_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Company Card 없음: {path}")
    return parse_company_card(path.read_text(encoding="utf-8"))


def save_company_card(
    card: CompanyCard, *, vault_path: Path | None = None
) -> Path:
    path = companies_dir(vault_path) / card.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_company_card(card), encoding="utf-8")
    return path


def list_company_cards(
    *, vault_path: Path | None = None
) -> list[CompanyCard]:
    d = companies_dir(vault_path)
    if not d.is_dir():
        return []
    cards: list[CompanyCard] = []
    for p in sorted(d.glob("*.md")):
        try:
            cards.append(parse_company_card(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(cards, key=lambda c: c.company_id)
