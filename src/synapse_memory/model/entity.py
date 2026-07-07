"""Single typed entity model."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from synapse_memory.model.frontmatter import parse_frontmatter, serialize_frontmatter
from synapse_memory.model.schema import entity_types, fields_for, relation_fields, statuses_for

ENTITY_TYPES = entity_types()
RELATION_FIELDS = relation_fields()
COMMON_FIELDS: tuple[str, ...] = (
    "slug",
    "title",
    "type",
    "status",
    "created",
    "updated",
    "sources",
    "related",
)
OBSERVED_AT_TYPES: tuple[str, ...] = ("insight", "log")
SUPERSEDED_STATUS = "superseded"
_SOURCE_TIME_KEYS = ("created", "created_at", "observed_at", "timestamp", "time", "date")
_SOURCE_TIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:]{5,}(?:Z|[+-]\d{2}:?\d{2})?)?"
)


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
    status: str = ""
    created: str | None = None
    updated: str = ""
    observed_at: str | None = None
    sources: tuple[Any, ...] = ()
    body: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)
    related: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()
    part_of: tuple[str, ...] = ()
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
        attrs = dict(self.attrs or {})
        legacy_created = attrs.pop("created", "")
        legacy_observed_at = attrs.pop("observed_at", "")
        legacy_related = attrs.pop("related", ())
        if not self.status:
            statuses = statuses_for(self.type)
            self.status = statuses[0] if statuses else "active"
        if self.created is None:
            self.created = str(legacy_created or _now_iso())
        elif not self.created and legacy_created:
            self.created = str(legacy_created)
        else:
            self.created = str(self.created or "")
        if self.type in OBSERVED_AT_TYPES:
            if self.observed_at is None:
                self.observed_at = str(legacy_observed_at or self.created)
            elif not self.observed_at and legacy_observed_at:
                self.observed_at = str(legacy_observed_at)
            else:
                self.observed_at = str(self.observed_at or "")
        else:
            self.observed_at = ""
        if self.updated:
            try:
                date.fromisoformat(str(self.updated))
            except ValueError as exc:
                raise ValueError(f"updated 형식 오류 (YYYY-MM-DD 필요): {self.updated!r}") from exc
        self.sources = tuple(_normalize_value(value) for value in _as_sequence(self.sources))
        self.related = tuple(
            str(value) for value in _as_sequence(self.related or legacy_related)
        )
        for key in RELATION_FIELDS:
            setattr(self, key, tuple(str(value) for value in _as_sequence(getattr(self, key))))
        self.attrs = _normalize_attrs(self.type, attrs)

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
    def last_reviewed(self) -> str:
        return str(self.attrs.get("last_reviewed") or "")

    @last_reviewed.setter
    def last_reviewed(self, value: str) -> None:
        self.attrs["last_reviewed"] = value

    def __getattr__(self, name: str) -> Any:
        if name in self.attrs:
            return self.attrs[name]
        raise AttributeError(name)

    @property
    def is_superseded(self) -> bool:
        return self.status.lower() == SUPERSEDED_STATUS

    @property
    def is_current(self) -> bool:
        return not self.is_superseded


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
    if entity.created:
        meta["created"] = entity.created
    if entity.updated:
        meta["updated"] = entity.updated
    if entity.type in OBSERVED_AT_TYPES and entity.observed_at:
        meta["observed_at"] = entity.observed_at
    if entity.sources:
        meta["sources"] = [_plain_value(source) for source in entity.sources]
    if entity.related:
        meta["related"] = list(entity.related)
    for key in RELATION_FIELDS:
        values = tuple(getattr(entity, key) or ())
        if values:
            meta[key] = list(values)
    for key, value in entity.attrs.items():
        if key in COMMON_FIELDS or key in RELATION_FIELDS or key == "observed_at":
            continue
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
        if key not in COMMON_FIELDS
        and key not in RELATION_FIELDS
        and key != "observed_at"
        and key != "related"
        and key in meta
        and meta[key] is not None
    }
    relation_values = {
        key: tuple(str(value) for value in _as_sequence(meta.get(key)))
        for key in RELATION_FIELDS
    }
    return Entity(
        slug=str(slug),
        title=str(title),
        type=entity_type,
        status=str(meta.get("status") or ""),
        created=str(meta.get("created") or ""),
        updated=str(meta.get("updated") or ""),
        observed_at=str(meta.get("observed_at") or ""),
        sources=tuple(_as_sequence(meta.get("sources"))),
        body=body,
        attrs=attrs,
        related=tuple(str(value) for value in _as_sequence(meta.get("related"))),
        **relation_values,
    )


def backfill_created(entity: Entity, *, recorded_at: str | None = None) -> Entity:
    """Return an Entity with created filled from git time or source timestamps."""
    if entity.created:
        return entity
    created = recorded_at or _first_source_timestamp(entity.sources)
    if not created:
        return entity
    return replace(entity, created=created)


def current_entities(entities: Iterable[Entity]) -> tuple[Entity, ...]:
    """Filter entities for current-answer retrieval."""
    return tuple(entity for entity in entities if entity.is_current)


def supersedes_history(entities: Iterable[Entity], start: str) -> tuple[Entity, ...]:
    """Walk newest-to-oldest through supersedes relations."""
    by_ref = _entity_ref_index(entities)
    root = _resolve_entity_ref(start, by_ref)
    if root is None:
        return ()

    history: list[Entity] = []
    seen: set[str] = set()

    def walk(entity: Entity) -> None:
        key = _entity_ref(entity)
        if key in seen:
            return
        seen.add(key)
        history.append(entity)
        for ref in entity.supersedes:
            previous = _resolve_entity_ref(ref, by_ref)
            if previous is not None:
                walk(previous)

    walk(root)
    return tuple(history)


def _normalize_attrs(entity_type: str, attrs: dict[str, Any]) -> dict[str, Any]:
    allowed = fields_for(entity_type)
    normalized: dict[str, Any] = {}
    for key, value in attrs.items():
        if key not in allowed:
            continue
        normalized[key] = _normalize_value(value)
    return normalized


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _first_source_timestamp(sources: Iterable[Any]) -> str:
    for source in sources:
        value = _source_timestamp(source)
        if value:
            return value
    return ""


def _source_timestamp(source: Any) -> str:
    if isinstance(source, AttrDict) or hasattr(source, "to_dict"):
        source = source.to_dict()
    if isinstance(source, dict):
        for key in _SOURCE_TIME_KEYS:
            value = source.get(key)
            if value:
                return str(value)
        return ""
    if isinstance(source, str):
        match = _SOURCE_TIME_RE.search(source)
        return match.group(0) if match else ""
    return ""


def _entity_ref(entity: Entity) -> str:
    return f"{entity.type}:{entity.slug}"


def _entity_ref_index(entities: Iterable[Entity]) -> dict[str, Entity]:
    index: dict[str, Entity] = {}
    for entity in entities:
        index.setdefault(entity.slug, entity)
        index[_entity_ref(entity)] = entity
    return index


def _resolve_entity_ref(ref: str, index: dict[str, Entity]) -> Entity | None:
    return index.get(ref) or index.get(ref.split(":", 1)[-1])


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
