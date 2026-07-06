"""Project Card — yaml frontmatter + markdown body 형식.

Vault에 저장되며 사람이 직접 편집 가능. Python에서도 parse/serialize.

저장 위치: ``<vault>/20_Reference/Projects/<project_id>.md``

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from synapse_memory.config import get_config, get_vault_path

DEFAULT_PROJECTS_SUBPATH = Path("20_Reference") / "Projects"
FRONTMATTER_DELIMITER = "---"

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)
_SLUG_RE = re.compile(r"[^a-zA-Z0-9가-힣\-_]+")


# ---------------------------------------------------------------------------
# 모델
# ---------------------------------------------------------------------------


@dataclass
class ProjectMetric:
    """수치 지표. before/after 또는 단발 value."""

    name: str
    before: str | None = None
    after: str | None = None
    value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        if self.before is not None:
            d["before"] = self.before
        if self.after is not None:
            d["after"] = self.after
        if self.value is not None:
            d["value"] = self.value
        return d


@dataclass
class ProjectSource:
    """Card가 추출된 출처 — 감사 + 재추출 trace용."""

    type: str   # "obsidian" | "claude_code" | "manual"
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "path": self.path}


@dataclass
class ProjectCard:
    """이력서·면접 자산의 진실원본 단위.

    필수 필드: project_id, display_name. 그 외는 점진 채움 가능.
    """

    project_id: str
    display_name: str
    status: str = "active"
    role: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    team_size: int | None = None
    domains: list[str] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    metrics: list[ProjectMetric] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    sources: list[ProjectSource] = field(default_factory=list)
    confidence: float = 1.0
    created: str = ""
    last_reviewed: str = ""
    body: str = ""

    @property
    def filename(self) -> str:
        return f"{self.project_id}.md"


# ---------------------------------------------------------------------------
# 직렬화
# ---------------------------------------------------------------------------


def _frontmatter_dict(card: ProjectCard) -> dict[str, Any]:
    """body 제외 모든 필드를 dict로. None/빈 값은 생략 — 깔끔한 yaml."""
    d: dict[str, Any] = {
        "project_id": card.project_id,
        "display_name": card.display_name,
        "status": card.status,
    }
    optional_scalars = {
        "role": card.role,
        "period_start": card.period_start,
        "period_end": card.period_end,
        "team_size": card.team_size,
    }
    for k, v in optional_scalars.items():
        if v is not None and v != "":
            d[k] = v

    if card.domains:
        d["domains"] = card.domains
    if card.stack:
        d["stack"] = card.stack
    if card.keywords:
        d["keywords"] = card.keywords
    if card.metrics:
        d["metrics"] = [m.to_dict() for m in card.metrics]
    if card.links:
        d["links"] = card.links
    if card.sources:
        d["sources"] = [s.to_dict() for s in card.sources]

    d["confidence"] = card.confidence
    if card.created:
        d["created"] = card.created
    if card.last_reviewed:
        d["last_reviewed"] = card.last_reviewed
    return d


def serialize_project_card(card: ProjectCard) -> str:
    """Card → markdown 문자열 (yaml frontmatter + body)."""
    fm = _frontmatter_dict(card)
    yaml_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    body = card.body.lstrip("\n")
    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}"


def parse_project_card(text: str) -> ProjectCard:
    """markdown 문자열 → ProjectCard.

    Raises:
        ValueError: frontmatter 없음, 필수 필드 누락, yaml 오류.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("frontmatter (--- ... ---) 없음")

    yaml_text = m.group("yaml")
    body = m.group("body")

    try:
        meta = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc

    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")

    project_id = meta.get("project_id")
    display_name = meta.get("display_name")
    if not project_id or not display_name:
        raise ValueError("필수 필드 누락: project_id, display_name")

    metrics = [
        ProjectMetric(
            name=m["name"],
            before=m.get("before"),
            after=m.get("after"),
            value=m.get("value"),
        )
        for m in meta.get("metrics", []) or []
        if isinstance(m, dict) and "name" in m
    ]
    sources = [
        ProjectSource(type=s["type"], path=s["path"])
        for s in meta.get("sources", []) or []
        if isinstance(s, dict) and "type" in s and "path" in s
    ]

    return ProjectCard(
        project_id=str(project_id),
        display_name=str(display_name),
        status=str(meta.get("status", "active")),
        role=meta.get("role"),
        period_start=meta.get("period_start"),
        period_end=meta.get("period_end"),
        team_size=meta.get("team_size"),
        domains=list(meta.get("domains") or []),
        stack=list(meta.get("stack") or []),
        keywords=list(meta.get("keywords") or []),
        metrics=metrics,
        links=list(meta.get("links") or []),
        sources=sources,
        confidence=float(meta.get("confidence", 1.0)),
        created=str(meta.get("created", "")),
        last_reviewed=str(meta.get("last_reviewed", "")),
        body=body,
    )


# ---------------------------------------------------------------------------
# 디스크 I/O
# ---------------------------------------------------------------------------


def projects_dir(vault_path: Path | None = None) -> Path:
    """Project Card 저장 디렉토리. ``<vault>/20_Reference/Projects``."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / get_config().vault_folders.reference.projects


def slugify(name: str) -> str:
    """display_name → file-safe slug. 한국어 음절 보존, 공백 → ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def load_project_card(
    project_id: str, *, vault_path: Path | None = None
) -> ProjectCard:
    """ID로 Card 로드.

    Raises:
        FileNotFoundError: 해당 Card 파일 없음.
    """
    path = projects_dir(vault_path) / f"{project_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Project Card 없음: {path}")
    return parse_project_card(path.read_text(encoding="utf-8"))


def save_project_card(
    card: ProjectCard, *, vault_path: Path | None = None
) -> Path:
    """Card → vault 디스크. 디렉토리 자동 생성. 기존 파일은 덮어씀.

    Returns:
        저장된 절대 경로.
    """
    path = projects_dir(vault_path) / card.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_project_card(card), encoding="utf-8")
    return path


def list_project_cards(
    *, vault_path: Path | None = None
) -> list[ProjectCard]:
    """vault 안 모든 Project Card 로드 (parse 실패는 skip).

    Returns:
        project_id 알파벳순.
    """
    d = projects_dir(vault_path)
    if not d.is_dir():
        return []
    cards: list[ProjectCard] = []
    for p in sorted(d.glob("*.md")):
        try:
            cards.append(parse_project_card(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(cards, key=lambda c: c.project_id)
