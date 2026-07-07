"""Entity lint — schema.yaml 검증 + 구조 자동 수정 (순수 Python, LLM 불필요).

R3 원칙: "구조는 자동, 진실은 사람".
- 구조 결함(끊긴 역링크, 죽은 링크)은 자동 수정.
- schema.yaml 위반은 plain report로만 보고.

분석기(find_*)는 list[Entity] 입력의 순수 함수 — 결정적, 디스크 불필요.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

import dataclasses
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse_memory.config import get_vault_path
from synapse_memory.model import (
    Entity,
    folder_for,
    load_schema,
    parse_frontmatter,
    relation_fields,
    uses_year_month_folder,
)
from synapse_memory.retrieval.pages import _all_pages
from synapse_memory.store import save_page
from synapse_memory.wiki.links import link_target
from synapse_memory.wiki.log import append_log

COMMON_REQUIRED_FIELDS = ("type", "slug", "title", "status")
INDEX_PATHS = ("index.md", "90_System/AI/index.md")
INDEX_COUNT_RE = re.compile(
    r"(?:total[_ -]?pages|pages[_ -]?total|pages checked|총 페이지 수)\s*[:=]\s*(\d+)",
    re.IGNORECASE,
)


def _targets(page: Entity) -> list[str]:
    """page.related의 각 링크에서 slug 대상을 추출 (등장순, 중복 제거)."""
    seen: dict[str, None] = {}
    for link in page.related:
        target = link_target(link)
        if target and target not in seen:
            seen[target] = None
    return list(seen.keys())


def find_dead_links(pages: list[Entity]) -> list[tuple[str, str]]:
    """A의 링크 대상이 pages에 없으면 (A, target)."""
    existing = {p.slug for p in pages}
    dead: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        for target in _targets(page):
            if target not in existing:
                pair = (page.slug, target)
                if pair not in seen:
                    seen.add(pair)
                    dead.append(pair)
    return dead


# ---------------------------------------------------------------------------
# 구조 자동 수정
# ---------------------------------------------------------------------------


@dataclass
class LintViolation:
    """schema.yaml validation violation."""

    code: str
    path: str
    message: str


@dataclass
class LintReport:
    """lint 1회 실행 결과 요약."""

    dead_links_removed: int = 0
    pages_checked: int = 0
    validation_violations: tuple[LintViolation, ...] = ()
    index_checked: bool = False
    index_expected_pages: int | None = None
    index_actual_pages: int | None = None

    @property
    def violation_count(self) -> int:
        return len(self.validation_violations)

    @property
    def has_violations(self) -> bool:
        return bool(self.validation_violations)

    def render_plain(self) -> str:
        """Plain terminal/markdown report."""
        lines = [
            f"lint (schema.yaml): {self.pages_checked} pages checked",
            f"dead_links_removed: {self.dead_links_removed}",
        ]
        if self.index_checked:
            lines.append(
                "index freshness: "
                f"expected={self.index_expected_pages} actual={self.index_actual_pages}"
            )
        else:
            lines.append("index freshness: no index count found")
        lines.append(f"validation_violations: {self.violation_count}")
        for violation in self.validation_violations:
            lines.append(
                f"- [{violation.code}] {violation.path}: {violation.message}"
            )
        return "\n".join(lines)


def apply_structural_fixes(*, vault_path: Path | None = None) -> LintReport:
    """죽은 forward 링크 제거. 멱등."""
    report = LintReport()

    pages = _all_pages(vault_path=vault_path)
    dead = set(find_dead_links(pages))
    dead_targets_by_slug: dict[str, set[str]] = {}
    for src, target in dead:
        dead_targets_by_slug.setdefault(src, set()).add(target)
    for source_page in pages:
        bad = dead_targets_by_slug.get(source_page.slug)
        if not bad:
            continue
        kept = tuple(
            link for link in source_page.related if link_target(link) not in bad
        )
        removed = len(source_page.related) - len(kept)
        if removed:
            save_page(dataclasses.replace(source_page, related=kept), vault_path=vault_path)
            report.dead_links_removed += removed

    return report


# ---------------------------------------------------------------------------
# schema.yaml 검증
# ---------------------------------------------------------------------------


def validate_schema_rules(*, vault_path: Path | None = None) -> LintReport:
    """schema.yaml 기반 frontmatter/folder/relation/index 검증."""
    root = _vault_root(vault_path)
    schema = load_schema()
    paths = _entity_markdown_paths(root, schema)
    violations: list[LintViolation] = []
    page_types_by_slug: dict[str, set[str]] = {}
    parsed_pages: list[tuple[Path, dict[str, Any]]] = []

    for path in paths:
        rel_path = _rel(path, root)
        try:
            meta, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            violations.append(
                LintViolation(
                    "frontmatter_parse",
                    rel_path,
                    f"frontmatter를 읽을 수 없습니다: {exc}",
                )
            )
            continue

        parsed_pages.append((path, meta))
        page_type = meta.get("type")
        slug = meta.get("slug")
        if isinstance(page_type, str) and isinstance(slug, str) and slug:
            page_types_by_slug.setdefault(slug, set()).add(page_type)

    for path, meta in parsed_pages:
        violations.extend(_validate_page(path, meta, root, schema, page_types_by_slug))

    expected = _index_expected_pages(root)
    violations.extend(_validate_index_freshness(root, len(paths), expected))
    return LintReport(
        pages_checked=len(parsed_pages),
        validation_violations=tuple(violations),
        index_checked=expected is not None,
        index_expected_pages=expected,
        index_actual_pages=len(paths) if expected is not None else None,
    )


# ---------------------------------------------------------------------------
# 전체 lint 오케스트레이션
# ---------------------------------------------------------------------------


def run_lint(
    *,
    vault_path: Path | None = None,
    today: str | None = None,
) -> LintReport:
    """구조 자동 수정 → schema 검증 → log 기록."""
    _ = today
    fix_report = apply_structural_fixes(vault_path=vault_path)
    validation_report = validate_schema_rules(vault_path=vault_path)
    report = dataclasses.replace(
        validation_report,
        dead_links_removed=fix_report.dead_links_removed,
    )

    with suppress(OSError):
        append_log(
            f"lint: -{report.dead_links_removed} dead, "
            f"{report.violation_count} schema violations",
        )
    return report


def _vault_root(vault_path: Path | None) -> Path:
    return (vault_path or get_vault_path()).expanduser().resolve()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _entity_markdown_paths(root: Path, schema: dict[str, Any]) -> tuple[Path, ...]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for spec in schema["types"].values():
        folder = spec.get("folder")
        if not isinstance(folder, str):
            continue
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(path)
    return tuple(paths)


def _validate_page(
    path: Path,
    meta: dict[str, Any],
    root: Path,
    schema: dict[str, Any],
    page_types_by_slug: dict[str, set[str]],
) -> tuple[LintViolation, ...]:
    rel_path = _rel(path, root)
    violations: list[LintViolation] = []
    types = schema["types"]
    page_type = meta.get("type")

    for field in COMMON_REQUIRED_FIELDS:
        if not meta.get(field):
            violations.append(
                LintViolation(
                    "missing_required",
                    rel_path,
                    f"필수 frontmatter field 누락: {field}",
                )
            )

    if page_type not in types:
        violations.append(
            LintViolation(
                "invalid_type",
                rel_path,
                f"type이 schema.yaml enum에 없습니다: {page_type!r}",
            )
        )
        return tuple(violations)

    page_type = str(page_type)
    slug = str(meta.get("slug") or "")
    status = meta.get("status")
    allowed_statuses = types[page_type].get("statuses") or ()
    if status and status not in allowed_statuses:
        violations.append(
            LintViolation(
                "invalid_enum",
                rel_path,
                f"status={status!r}; allowed={list(allowed_statuses)!r}",
            )
        )
    if slug and path.stem != slug:
        violations.append(
            LintViolation(
                "slug_filename_mismatch",
                rel_path,
                f"slug={slug!r} filename={path.stem!r}",
            )
        )
    if not _is_in_type_folder(path, root, page_type):
        violations.append(
            LintViolation(
                "type_folder_mismatch",
                rel_path,
                f"type={page_type!r}은 {folder_for(page_type)!r} 아래에 있어야 합니다",
            )
        )

    violations.extend(_validate_field_values(rel_path, meta, page_type, schema))
    violations.extend(
        _validate_relations(rel_path, meta, page_type, schema, page_types_by_slug)
    )
    return tuple(violations)


def _is_in_type_folder(path: Path, root: Path, page_type: str) -> bool:
    base = root / folder_for(page_type)
    try:
        relative = path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    if uses_year_month_folder(page_type):
        return len(relative.parts) >= 3
    return len(relative.parts) == 1


def _validate_field_values(
    rel_path: str,
    meta: dict[str, Any],
    page_type: str,
    schema: dict[str, Any],
) -> tuple[LintViolation, ...]:
    fields = schema["types"][page_type].get("fields") or {}
    violations: list[LintViolation] = []
    for field_name, field_spec in fields.items():
        if not isinstance(field_spec, dict):
            continue
        value = meta.get(field_name)
        if field_spec.get("required") and value in (None, "", []):
            violations.append(
                LintViolation(
                    "missing_required",
                    rel_path,
                    f"필수 typed field 누락: {field_name}",
                )
            )
        violations.extend(_validate_value(rel_path, field_name, value, field_spec))
    return tuple(violations)


def _validate_value(
    rel_path: str,
    field_path: str,
    value: Any,
    spec: dict[str, Any],
) -> tuple[LintViolation, ...]:
    if value is None:
        return ()
    field_type = spec.get("type")
    if field_type == "enum":
        allowed = spec.get("values") or ()
        if value not in allowed:
            return (
                LintViolation(
                    "invalid_enum",
                    rel_path,
                    f"{field_path}={value!r}; allowed={list(allowed)!r}",
                ),
            )
        return ()
    if field_type == "list":
        items = spec.get("items")
        if not isinstance(value, list) or not isinstance(items, dict):
            return ()
        violations: list[LintViolation] = []
        for index, item in enumerate(value):
            violations.extend(
                _validate_value(rel_path, f"{field_path}[{index}]", item, items)
            )
        return tuple(violations)
    if field_type == "object":
        fields = spec.get("fields") or {}
        if not isinstance(value, dict) or not isinstance(fields, dict):
            return ()
        violations = []
        for child_name, child_spec in fields.items():
            if not isinstance(child_spec, dict):
                continue
            child_value = value.get(child_name)
            child_path = f"{field_path}.{child_name}"
            if child_spec.get("required") and child_value in (None, "", []):
                violations.append(
                    LintViolation(
                        "missing_required",
                        rel_path,
                        f"필수 typed field 누락: {child_path}",
                    )
                )
            violations.extend(
                _validate_value(rel_path, child_path, child_value, child_spec)
            )
        return tuple(violations)
    return ()


def _validate_relations(
    rel_path: str,
    meta: dict[str, Any],
    page_type: str,
    schema: dict[str, Any],
    page_types_by_slug: dict[str, set[str]],
) -> tuple[LintViolation, ...]:
    violations: list[LintViolation] = []
    for relation in relation_fields():
        raw_values = meta.get(relation)
        if raw_values in (None, ""):
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        relation_spec = schema["relations"].get(relation) or {}
        domain = set(relation_spec.get("domain") or ())
        range_ = set(relation_spec.get("range") or ())
        if domain and page_type not in domain:
            violations.append(
                LintViolation(
                    "relation_domain",
                    rel_path,
                    f"{relation} domain 위반: source type={page_type!r}",
                )
            )
        for value in values:
            target_ref = link_target(str(value))
            explicit_type, target_slug = _relation_target(target_ref)
            target_types = page_types_by_slug.get(target_slug, set())
            if not target_types:
                violations.append(
                    LintViolation(
                        "relation_target_missing",
                        rel_path,
                        f"{relation} 대상 없음: {value!r}",
                    )
                )
                continue
            if explicit_type:
                if explicit_type not in target_types:
                    violations.append(
                        LintViolation(
                            "relation_target_missing",
                            rel_path,
                            f"{relation} 대상 type 불일치: {value!r}",
                        )
                    )
                    continue
                target_types = {explicit_type}
            if len(target_types) > 1:
                violations.append(
                    LintViolation(
                        "relation_target_ambiguous",
                        rel_path,
                        f"{relation} 대상 slug가 여러 type에 존재합니다: {target_slug!r}",
                    )
                )
                continue
            target_type = next(iter(target_types))
            if range_ and target_type not in range_:
                violations.append(
                    LintViolation(
                        "relation_range",
                        rel_path,
                        f"{relation} range 위반: target={target_slug!r} type={target_type!r}",
                    )
                )
    return tuple(violations)


def _relation_target(target: str) -> tuple[str | None, str]:
    if ":" in target:
        target_type, slug = target.split(":", 1)
        return target_type, slug
    return None, target


def _validate_index_freshness(
    root: Path,
    actual_pages: int,
    expected: int | None,
) -> tuple[LintViolation, ...]:
    if expected is None or expected == actual_pages:
        return ()
    return (
        LintViolation(
            "index_stale",
            "index.md",
            f"index total pages={expected}, actual pages={actual_pages}",
        ),
    )


def _index_expected_pages(root: Path) -> int | None:
    for rel_path in INDEX_PATHS:
        path = root / rel_path
        if not path.is_file():
            continue
        match = INDEX_COUNT_RE.search(path.read_text(encoding="utf-8"))
        if match:
            return int(match.group(1))
    return None
