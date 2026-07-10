"""Recipe markdown loader — frontmatter parse + validation + 32KB cap.

Spec: ``specs/007-persona-recipes/spec.md`` FR-015, FR-016, FR-019
Research: ``specs/007-persona-recipes/research.md`` R-2

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from synapse_memory.model import parse_frontmatter
from synapse_memory.recipes.recipe import (
    GenerationRecipe,
    InputRequirement,
    RecipeRagMode,
    RecipeSource,
)

SYSTEM_PROMPT_BYTE_CAP = 32_768  # FR-016 / Q4
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class RecipeValidationError(ValueError):
    """Recipe markdown 의 frontmatter / body 가 schema 위반일 때 발생."""


def _require_str(meta: dict[str, Any], key: str) -> str:
    val = meta.get(key)
    if not isinstance(val, str) or not val.strip():
        raise RecipeValidationError(f"required string field missing: {key}")
    return val.strip()


def _require_dict(
    meta: dict[str, Any], key: str, *, allow_empty: bool = True
) -> dict[str, Any]:
    if key not in meta:
        raise RecipeValidationError(f"required mapping field missing: {key}")
    val = meta.get(key)
    if val is None and allow_empty:
        return {}
    if not isinstance(val, dict):
        raise RecipeValidationError(f"field must be mapping: {key}")
    return val


def _normalize_input_schema(raw: dict[str, Any]) -> dict[str, InputRequirement]:
    out: dict[str, InputRequirement] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            raise RecipeValidationError(f"input_schema key must be non-empty string: {k!r}")
        sv = str(v).strip().lower()
        if sv not in {"required", "optional"}:
            raise RecipeValidationError(
                f"input_schema[{k!r}] must be 'required' or 'optional', got {v!r}"
            )
        out[k] = sv  # type: ignore[assignment]
    return out


def _validate_save_subpath(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecipeValidationError(f"save_subpath must be string or null: {value!r}")
    if not value.strip():
        return None
    if value.startswith("/"):
        raise RecipeValidationError(f"save_subpath must be vault-relative (no leading /): {value!r}")
    parts = [p for p in value.replace("\\", "/").split("/") if p]
    if ".." in parts:
        raise RecipeValidationError(f"save_subpath must not contain '..': {value!r}")
    if any(c in value for c in ("\x00", "\n", "\r")):
        raise RecipeValidationError(f"save_subpath contains illegal characters: {value!r}")
    return value.strip()


def _coerce_int(meta: dict[str, Any], key: str, default: int, *, lo: int, hi: int) -> int:
    if key not in meta:
        return default
    val = meta[key]
    if not isinstance(val, int) or isinstance(val, bool):
        raise RecipeValidationError(f"{key} must be int, got {type(val).__name__}")
    if not (lo <= val <= hi):
        raise RecipeValidationError(f"{key} must be in [{lo},{hi}], got {val}")
    return val


def _coerce_bool(meta: dict[str, Any], key: str, default: bool) -> bool:
    if key not in meta:
        return default
    val = meta[key]
    if not isinstance(val, bool):
        raise RecipeValidationError(f"{key} must be bool, got {type(val).__name__}")
    return val


def _coerce_rag_mode(meta: dict[str, Any]) -> RecipeRagMode:
    raw = str(meta.get("rag_mode", "dense")).strip().lower()
    if raw not in {"dense", "hybrid"}:
        raise RecipeValidationError(
            f"rag_mode must be 'dense' or 'hybrid', got {meta.get('rag_mode')!r}"
        )
    return raw  # type: ignore[return-value]


def parse_recipe(path: Path, *, source: RecipeSource) -> GenerationRecipe:
    """Recipe markdown 1 장을 ``GenerationRecipe`` 로 파싱."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecipeValidationError(f"cannot read recipe file {path}: {exc}") from exc

    try:
        meta, system_prompt = parse_frontmatter(text)
    except ValueError as exc:
        raise RecipeValidationError(f"frontmatter YAML parse failed in {path}: {exc}") from exc

    if not isinstance(meta, dict):
        raise RecipeValidationError(
            f"frontmatter must be a mapping, got {type(meta).__name__} in {path}"
        )

    name = _require_str(meta, "name")
    if not _NAME_RE.match(name):
        raise RecipeValidationError(
            f"recipe name '{name}' invalid: must match ^[a-z][a-z0-9_]{{0,63}}$"
        )

    description = _require_str(meta, "description")
    if len(description) > 200:
        raise RecipeValidationError(
            f"recipe description too long ({len(description)} chars, max 200)"
        )

    input_schema = _normalize_input_schema(_require_dict(meta, "input_schema"))

    rag_filter_raw = meta.get("rag_filter")
    if rag_filter_raw is None:
        rag_filter: dict[str, str] | None = None
    elif isinstance(rag_filter_raw, dict):
        rag_filter = {str(k): str(v) for k, v in rag_filter_raw.items()}
    else:
        raise RecipeValidationError(f"rag_filter must be mapping or null in {path}")

    rag_top_k = _coerce_int(meta, "rag_top_k", 8, lo=1, hi=50)
    rag_mode = _coerce_rag_mode(meta)
    use_profile = _coerce_bool(meta, "use_profile", True)
    save_subpath = _validate_save_subpath(meta.get("save_subpath"))
    locale_aware = _coerce_bool(meta, "locale_aware", True)
    domain_aware = _coerce_bool(meta, "domain_aware", False)
    timeout = _coerce_int(meta, "timeout", 120, lo=1, hi=600)
    raw_model = meta.get("model")
    model = str(raw_model).strip() if raw_model is not None else None
    if model == "":
        model = None

    system_prompt = system_prompt or ""
    if len(system_prompt.encode("utf-8")) > SYSTEM_PROMPT_BYTE_CAP:
        raise RecipeValidationError(
            f"recipe '{name}' system_prompt exceeds 32KB cap"
        )

    return GenerationRecipe(
        name=name,
        description=description,
        source=source,
        source_path=path,
        input_schema=input_schema,
        rag_filter=rag_filter,
        rag_top_k=rag_top_k,
        rag_mode=rag_mode,
        use_profile=use_profile,
        save_subpath=save_subpath,
        locale_aware=locale_aware,
        domain_aware=domain_aware,
        timeout=timeout,
        model=model,
        system_prompt=system_prompt,
    )
