"""Project entity compatibility helpers.

저장 위치: ``<vault>/Entities/Projects/<project_id>.md``
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from synapse_memory.config import get_config, get_vault_path
from synapse_memory.model import (
    Entity,
    attr_dict,
    parse_frontmatter,
    serialize_entity,
)

DEFAULT_PROJECTS_SUBPATH = Path("Entities") / "Projects"
_SLUG_RE = re.compile(r"[^a-zA-Z0-9가-힣\-_]+")

PROJECT_DEFAULT_ATTRS: dict[str, Any] = {
    "role": None,
    "period_start": None,
    "period_end": None,
    "domains": [],
    "stack": [],
    "keywords": [],
    "metrics": [],
    "confidence": 1.0,
    "last_reviewed": "",
}


def ProjectMetric(
    name: str,
    before: str | None = None,
    after: str | None = None,
    value: str | None = None,
) -> Any:
    """Project metric attr value."""
    return attr_dict(name=name, before=before, after=after, value=value)


def ProjectSource(type: str, path: str) -> Any:
    """Source attr value."""
    return attr_dict(type=type, path=path)


def ProjectCard(
    project_id: str,
    display_name: str,
    status: str = "active",
    role: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    domains: list[str] | None = None,
    stack: list[str] | None = None,
    keywords: list[str] | None = None,
    metrics: list[Any] | None = None,
    sources: list[Any] | None = None,
    confidence: float = 1.0,
    created: str | None = None,
    last_reviewed: str = "",
    supersedes: list[str] | None = None,
    body: str = "",
) -> Entity:
    """Compatibility constructor returning the single Entity model."""
    attrs = _project_attrs(
        role=role,
        period_start=period_start,
        period_end=period_end,
        domains=list(domains or []),
        stack=list(stack or []),
        keywords=list(keywords or []),
        metrics=list(metrics or []),
        confidence=confidence,
        last_reviewed=last_reviewed,
    )
    return Entity(
        slug=project_id,
        title=display_name,
        type="project",
        status=status,
        created=created,
        sources=tuple(sources or ()),
        body=body,
        attrs=attrs,
        supersedes=tuple(supersedes or ()),
    )


def serialize_project_card(card: Entity) -> str:
    """Card → markdown 문자열 (yaml frontmatter + body)."""
    return serialize_entity(card)


def parse_project_card(text: str) -> Entity:
    """markdown 문자열 → ProjectCard.

    Raises:
        ValueError: frontmatter 없음, 필수 필드 누락, yaml 오류.
    """
    meta, body = parse_frontmatter(text)
    if "type" not in meta:
        meta = {
            **meta,
            "type": "project",
            "slug": meta.get("project_id"),
            "title": meta.get("display_name"),
        }
    if meta.get("type") != "project":
        raise ValueError(f"알 수 없는 project type: {meta.get('type')!r}")
    project_id = meta.get("slug")
    display_name = meta.get("title")
    if not project_id or not display_name:
        raise ValueError("필수 필드 누락: project_id, display_name")
    return ProjectCard(
        project_id=str(project_id),
        display_name=str(display_name),
        status=str(meta.get("status", "active")),
        role=meta.get("role"),
        period_start=meta.get("period_start"),
        period_end=meta.get("period_end"),
        domains=list(meta.get("domains") or []),
        stack=list(meta.get("stack") or []),
        keywords=list(meta.get("keywords") or []),
        metrics=[
            ProjectMetric(
                name=m["name"],
                before=m.get("before"),
                after=m.get("after"),
                value=m.get("value"),
            )
            for m in meta.get("metrics", []) or []
            if isinstance(m, dict) and "name" in m
        ],
        sources=[
            ProjectSource(type=s["type"], path=s["path"])
            for s in meta.get("sources", []) or []
            if isinstance(s, dict) and "type" in s and "path" in s
        ],
        confidence=float(meta.get("confidence", 1.0)),
        created=str(meta.get("created", "")),
        last_reviewed=str(meta.get("last_reviewed", "")),
        supersedes=_relation_list(meta.get("supersedes")),
        body=body,
    )


# ---------------------------------------------------------------------------
# 디스크 I/O
# ---------------------------------------------------------------------------


def projects_dir(vault_path: Path | None = None) -> Path:
    """Project Card 저장 디렉토리. ``<vault>/Entities/Projects``."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / get_config().vault_folders.wiki.projects


def slugify(name: str) -> str:
    """display_name → file-safe slug. 한국어 음절 보존, 공백 → ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def load_project_card(
    project_id: str, *, vault_path: Path | None = None
) -> Entity:
    """ID로 Card 로드.

    Raises:
        FileNotFoundError: 해당 Card 파일 없음.
    """
    path = projects_dir(vault_path) / f"{project_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Project Card 없음: {path}")
    return parse_project_card(path.read_text(encoding="utf-8"))


def save_project_card(
    card: Entity, *, vault_path: Path | None = None
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
) -> list[Entity]:
    """vault 안 모든 Project Card 로드 (parse 실패는 skip).

    Returns:
        project_id 알파벳순.
    """
    d = projects_dir(vault_path)
    if not d.is_dir():
        return []
    cards: list[Entity] = []
    for p in sorted(d.glob("*.md")):
        try:
            cards.append(parse_project_card(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(cards, key=lambda c: c.project_id)


def _project_attrs(**values: Any) -> dict[str, Any]:
    return {**PROJECT_DEFAULT_ATTRS, **values}


def _relation_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
