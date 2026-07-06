"""Single typed entity model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from synapse_memory.model.frontmatter import parse_frontmatter, serialize_frontmatter
from synapse_memory.model.schema import entity_types, fields_for, relation_fields

ENTITY_TYPES = entity_types()
RELATION_FIELDS = relation_fields()
COMMON_FIELDS: tuple[str, ...] = ("slug", "title", "type", "status", "updated", "sources")


class AttrDict(dict[str, Any]):
    """Small dict with attribute access for legacy card call sites."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def to_dict(self) -> dict[str, Any]:
        return dict(self)


def attr_dict(**values: Any) -> AttrDict:
    """Build an AttrDict while dropping None values."""
    return AttrDict(
        {
            key: value
            for key, value in values.items()
            if value is not None
        }
    )


@dataclass
class Entity:
    """Single typed entity.

    Common and relation fields stay top-level. Schema-declared per-type values
    live in attrs and serialize as type-specific frontmatter keys.
    """

    slug: str
    title: str
    type: str
    status: str = "active"
    updated: str = ""
    sources: tuple[Any, ...] = ()
    body: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)
    uses: tuple[str, ...] = ()
    part_of: tuple[str, ...] = ()
    about: tuple[str, ...] = ()
    decided_in: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    same_as: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.type not in ENTITY_TYPES:
            raise ValueError(f"알 수 없는 type: {self.type!r}")
        if not self.slug:
            raise ValueError("필수 필드 누락: slug")
        if not self.title:
            raise ValueError("필수 필드 누락: title")
        if self.updated:
            try:
                date.fromisoformat(str(self.updated))
            except ValueError as exc:
                raise ValueError(f"updated 형식 오류 (YYYY-MM-DD 필요): {self.updated!r}") from exc
        self.sources = tuple(_normalize_value(value) for value in (self.sources or ()))
        for key in RELATION_FIELDS:
            setattr(self, key, tuple(getattr(self, key) or ()))
        self.attrs = _normalize_attrs(self.type, self.attrs)

    @property
    def filename(self) -> str:
        return f"{self.slug}.md"

    @property
    def project_id(self) -> str:
        return self.slug

    @project_id.setter
    def project_id(self, value: str) -> None:
        self.slug = value

    @property
    def company_id(self) -> str:
        return self.slug

    @company_id.setter
    def company_id(self, value: str) -> None:
        self.slug = value

    @property
    def insight_id(self) -> str:
        return self.slug

    @insight_id.setter
    def insight_id(self, value: str) -> None:
        self.slug = value

    @property
    def display_name(self) -> str:
        return self.title

    @display_name.setter
    def display_name(self, value: str) -> None:
        self.title = value

    @property
    def question(self) -> str:
        return str(self.attrs.get("question") or self.title)

    @question.setter
    def question(self, value: str) -> None:
        self.attrs["question"] = value
        self.title = value

    @property
    def command(self) -> str:
        return str(self.attrs.get("command") or "")

    @command.setter
    def command(self, value: str) -> None:
        self.attrs["command"] = value

    @property
    def created(self) -> str:
        return str(self.attrs.get("created") or "")

    @created.setter
    def created(self, value: str) -> None:
        self.attrs["created"] = value

    @property
    def last_reviewed(self) -> str:
        return str(self.attrs.get("last_reviewed") or "")

    @last_reviewed.setter
    def last_reviewed(self, value: str) -> None:
        self.attrs["last_reviewed"] = value

    def __getattr__(self, name: str) -> Any:
        if name in self.attrs:
            return self.attrs[name]
        raise AttributeError(name)


def parse_entity(text: str) -> Entity:
    """Markdown text -> Entity."""
    meta, body = parse_frontmatter(text)
    return entity_from_meta(meta, body)


def serialize_entity(entity: Entity) -> str:
    """Entity -> Markdown text."""
    if entity.type not in ENTITY_TYPES:
        raise ValueError(f"알 수 없는 type: {entity.type!r}")
    meta: dict[str, Any] = {
        "type": entity.type,
        "slug": entity.slug,
        "title": entity.title,
    }
    if entity.status:
        meta["status"] = entity.status
    if entity.updated:
        meta["updated"] = entity.updated
    if entity.sources:
        meta["sources"] = [_plain_value(source) for source in entity.sources]
    for key in RELATION_FIELDS:
        values = tuple(getattr(entity, key) or ())
        if values:
            meta[key] = list(values)
    for key, value in entity.attrs.items():
        if value is not None and value != "" and value != []:
            meta[key] = _plain_value(value)
    return serialize_frontmatter(meta, entity.body)


def entity_from_meta(meta: dict[str, Any], body: str = "") -> Entity:
    """Build Entity from already parsed frontmatter metadata."""
    entity_type = str(meta.get("type") or "")
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"알 수 없는 type: {entity_type!r}")
    slug = meta.get("slug")
    title = meta.get("title")
    if not slug:
        raise ValueError("필수 필드 누락: slug")
    if not title:
        raise ValueError("필수 필드 누락: title")

    typed_fields = fields_for(entity_type)
    attrs = {
        key: meta[key]
        for key in typed_fields
        if key in meta and meta[key] is not None
    }
    relation_values = {
        key: tuple(str(value) for value in (meta.get(key) or []))
        for key in RELATION_FIELDS
    }
    return Entity(
        slug=str(slug),
        title=str(title),
        type=entity_type,
        status=str(meta.get("status") or "active"),
        updated=str(meta.get("updated") or ""),
        sources=tuple(meta.get("sources") or ()),
        body=body,
        attrs=attrs,
        **relation_values,
    )


def _normalize_attrs(entity_type: str, attrs: dict[str, Any]) -> dict[str, Any]:
    allowed = fields_for(entity_type)
    normalized: dict[str, Any] = {}
    for key, value in attrs.items():
        if key not in allowed:
            continue
        normalized[key] = _normalize_value(value)
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, AttrDict):
        return value
    if isinstance(value, dict):
        return AttrDict({key: _normalize_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    return value


def _plain_value(value: Any) -> Any:
    if isinstance(value, AttrDict):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, dict):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if hasattr(value, "to_dict"):
        return _plain_value(value.to_dict())
    return value
