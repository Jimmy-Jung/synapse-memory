"""Entity schema loading."""
from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

SCHEMA_RESOURCE = "schema.yaml"
RELATION_FIELDS: tuple[str, ...] = (
    "uses",
    "part_of",
    "broader",
    "decided_in",
    "supersedes",
    "same_as",
)


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Load and validate the packaged entity schema."""
    schema_text = resources.files("synapse_memory").joinpath(SCHEMA_RESOURCE).read_text(
        encoding="utf-8"
    )
    loaded = yaml.safe_load(schema_text)
    if not isinstance(loaded, dict):
        raise ValueError("schema.yaml root must be a mapping")
    _validate_schema(loaded)
    return loaded


def entity_types() -> tuple[str, ...]:
    """Schema-declared entity type vocabulary."""
    return tuple(load_schema()["types"].keys())


def relation_fields() -> tuple[str, ...]:
    """Schema-declared relation frontmatter keys."""
    return tuple(load_schema()["relations"].keys())


def fields_for(entity_type: str) -> dict[str, Any]:
    """Schema-declared typed attrs for an entity type."""
    types = load_schema()["types"]
    if entity_type not in types:
        raise ValueError(f"알 수 없는 type: {entity_type!r}")
    fields = types[entity_type].get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError(f"schema fields must be a mapping for {entity_type!r}")
    return fields


def statuses_for(entity_type: str) -> tuple[str, ...]:
    """Schema-declared status values for an entity type."""
    types = load_schema()["types"]
    if entity_type not in types:
        raise ValueError(f"알 수 없는 type: {entity_type!r}")
    statuses = types[entity_type].get("statuses") or ()
    return tuple(str(status) for status in statuses)


def folder_for(entity_type: str) -> str:
    """Vault folder declared for an entity type."""
    types = load_schema()["types"]
    if entity_type not in types:
        raise ValueError(f"알 수 없는 type: {entity_type!r}")
    folder = types[entity_type].get("folder")
    if not isinstance(folder, str) or not folder:
        raise ValueError(f"schema folder missing for {entity_type!r}")
    return folder


def uses_year_month_folder(entity_type: str) -> bool:
    """Whether this type uses year/month folders under its base folder."""
    types = load_schema()["types"]
    if entity_type not in types:
        raise ValueError(f"알 수 없는 type: {entity_type!r}")
    return bool(types[entity_type].get("year_month"))


def render_schema_guidance() -> str:
    """Render agent-facing schema rules from schema.yaml."""
    schema = load_schema()
    lines = [
        "schema.yaml 기준 검증 규칙:",
        "- 모든 페이지 frontmatter에는 type, slug, title, status가 필요합니다.",
        "- slug는 파일명(.md 제외)과 같아야 합니다.",
        "- type별 폴더와 status enum은 아래 선언을 따릅니다.",
    ]
    for entity_type, spec in schema["types"].items():
        statuses = ", ".join(spec.get("statuses") or ())
        folder = spec.get("folder")
        year_month = " (YYYY/MM 하위 폴더)" if spec.get("year_month") else ""
        lines.append(f"  - {entity_type}: {folder}{year_month}; status={statuses}")
        fields = spec.get("fields") or {}
        if fields:
            rendered = ", ".join(
                f"{name}={_render_field_spec(field_spec)}"
                for name, field_spec in fields.items()
                if isinstance(field_spec, dict)
            )
            lines.append(f"    fields: {rendered}")
    lines.append("- typed relation은 domain/range를 지켜야 합니다.")
    for relation, spec in schema["relations"].items():
        domain = ", ".join(spec.get("domain") or ())
        range_ = ", ".join(spec.get("range") or ())
        lines.append(f"  - {relation}: domain={domain}; range={range_}")
    return "\n".join(lines)


def _render_field_spec(spec: dict[str, Any]) -> str:
    field_type = str(spec.get("type") or "any")
    if field_type == "enum":
        values = ", ".join(str(value) for value in (spec.get("values") or ()))
        return f"enum[{values}]"
    if field_type == "list":
        items = spec.get("items")
        if isinstance(items, dict):
            return f"list<{_render_field_spec(items)}>"
        return "list"
    if field_type == "object":
        fields = spec.get("fields") or {}
        if isinstance(fields, dict):
            children = ", ".join(
                f"{name}:{_render_field_spec(child)}"
                for name, child in fields.items()
                if isinstance(child, dict)
            )
            return f"object{{{children}}}"
    return field_type


def _validate_schema(schema: dict[str, Any]) -> None:
    types = schema.get("types")
    relations = schema.get("relations")
    if not isinstance(types, dict) or not types:
        raise ValueError("schema.yaml requires non-empty types")
    if "person" in types:
        raise ValueError("person type is intentionally removed")
    expected_types = ("project", "company", "concept", "insight", "log", "profile")
    if tuple(types.keys()) != expected_types:
        raise ValueError(f"schema type vocabulary mismatch: {tuple(types.keys())!r}")
    if not isinstance(relations, dict):
        raise ValueError("schema.yaml requires relations mapping")
    missing = set(RELATION_FIELDS) - set(relations)
    if missing:
        raise ValueError(f"schema missing relation fields: {sorted(missing)!r}")
