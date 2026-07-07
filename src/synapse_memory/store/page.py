"""Vault-backed page and entity storage.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from synapse_memory.config import get_vault_path
from synapse_memory.folders import year_month_path
from synapse_memory.model import (
    ENTITY_TYPES,
    Entity,
    current_entities,
    folder_for,
    parse_entity,
    serialize_entity,
    uses_year_month_folder,
)


def _vault_root(vault_path: Path | None = None) -> Path:
    """Resolve the active vault root through the config SSOT unless overridden."""
    return (vault_path or get_vault_path()).expanduser().resolve()


def _type_base(page_type: str, vault_path: Path | None = None) -> Path:
    """타입별 schema 선언 루트."""
    return _vault_root(vault_path) / folder_for(page_type)


def page_dir(
    page_type: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> Path:
    """페이지 타입별 저장 디렉토리. year_month 타입은 연/월 하위폴더 사용."""
    if page_type not in ENTITY_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    base = _type_base(page_type, vault_path)
    if uses_year_month_folder(page_type):
        return year_month_path(base, when or date.today())
    return base


def _dated_folder_when(page: object) -> date:
    """updated(YYYY-MM-DD)로 연/월 폴더 결정. 없거나 깨졌으면 today."""
    updated = str(getattr(page, "updated", "") or "")
    if updated:
        try:
            return date.fromisoformat(updated)
        except ValueError:
            pass
    return date.today()


def page_path(page: Entity, *, vault_path: Path | None = None) -> Path:
    """페이지/엔티티의 디스크 경로."""
    when = _dated_folder_when(page) if uses_year_month_folder(page.type) else None
    return page_dir(page.type, vault_path=vault_path, when=when) / page.filename


def save_page(page: Entity, *, vault_path: Path | None = None) -> Path:
    """Entity -> vault 디스크. 디렉토리 자동 생성. 기존 파일 덮어씀."""
    path = page_path(page, vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entity(page), encoding="utf-8")
    return path


def load_page(
    page_type: str,
    slug: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> Entity:
    """타입+slug로 Entity 로드."""
    path = _entity_file_path(page_type, slug, vault_path=vault_path, when=when)
    if not path.is_file():
        raise FileNotFoundError(f"entity 없음: {path}")
    return parse_entity(path.read_text(encoding="utf-8"))


def list_pages(
    page_type: str,
    *,
    vault_path: Path | None = None,
) -> list[Entity]:
    """해당 타입 모든 Entity 로드. parse 실패는 skip."""
    pages: list[Entity] = []
    for path in _iter_markdown_paths(page_type, vault_path=vault_path):
        try:
            pages.append(parse_entity(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(pages, key=lambda page: page.slug)


def entity_path(entity: Entity, *, vault_path: Path | None = None) -> Path:
    """Entity의 디스크 경로."""
    return page_path(entity, vault_path=vault_path)


def save_entity(entity: Entity, *, vault_path: Path | None = None) -> Path:
    """Entity -> vault 디스크. 디렉토리 자동 생성. 기존 파일 덮어씀."""
    path = entity_path(entity, vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entity(entity), encoding="utf-8")
    return path


def load_entity(
    entity_type: str,
    slug: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> Entity:
    """타입+slug로 Entity 로드."""
    path = _entity_file_path(entity_type, slug, vault_path=vault_path, when=when)
    if not path.is_file():
        raise FileNotFoundError(f"entity 없음: {path}")
    return parse_entity(path.read_text(encoding="utf-8"))


def list_entities(
    entity_type: str,
    *,
    vault_path: Path | None = None,
) -> list[Entity]:
    """해당 타입 모든 Entity 로드. parse 실패는 skip."""
    entities: list[Entity] = []
    for path in _iter_markdown_paths(entity_type, vault_path=vault_path):
        try:
            entities.append(parse_entity(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(entities, key=lambda entity: entity.slug)


def list_current_entities(
    entity_type: str,
    *,
    vault_path: Path | None = None,
) -> list[Entity]:
    """해당 타입 Entity 중 현재형 답변 후보만 로드."""
    return list(current_entities(list_entities(entity_type, vault_path=vault_path)))


def _entity_file_path(
    entity_type: str,
    slug: str,
    *,
    vault_path: Path | None,
    when: date | None,
) -> Path:
    if "/" in slug or "\\" in slug:
        raise ValueError(f"잘못된 slug (경로 구분자 포함): {slug!r}")
    return page_dir(entity_type, vault_path=vault_path, when=when) / f"{slug}.md"


def _iter_markdown_paths(
    entity_type: str,
    *,
    vault_path: Path | None,
) -> list[Path]:
    base = (
        _type_base(entity_type, vault_path)
        if uses_year_month_folder(entity_type)
        else page_dir(entity_type, vault_path=vault_path)
    )
    if not base.is_dir():
        return []
    return list(base.rglob("*.md"))
