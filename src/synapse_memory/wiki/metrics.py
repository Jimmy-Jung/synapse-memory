"""Wiki relation coverage metrics.

Author: JunyoungJung
Created: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from synapse_memory.model import ENTITY_TYPES, RELATION_FIELDS, Entity
from synapse_memory.retrieval.pages import _all_pages
from synapse_memory.store import list_current_entities

MetricValue = int | float


def calculate_relation_metrics(entities: Iterable[Entity]) -> dict[str, MetricValue]:
    """Calculate relation coverage metrics from Entity objects."""
    pages = tuple(entities)
    total = len(pages)
    typed_pages = sum(1 for page in pages if _has_typed_relation(page))
    legacy_related_only = sum(
        1 for page in pages if _has_related(page) and not _has_typed_relation(page)
    )
    orphan_pages = sum(
        1 for page in pages if not _has_related(page) and not _has_typed_relation(page)
    )

    return {
        "total_pages": total,
        "typed_relation_pages": typed_pages,
        "typed_relation_coverage": _ratio(typed_pages, total),
        "legacy_related_residual_count": legacy_related_only,
        "legacy_related_residual_ratio": _ratio(legacy_related_only, total),
        "orphan_pages": orphan_pages,
        "orphan_ratio": _ratio(orphan_pages, total),
    }


def calculate_relation_metrics_for_vault(
    vault_path: Path | str | None = None,
    *,
    current_only: bool = False,
) -> dict[str, MetricValue]:
    """Load Entity pages through existing loaders and calculate relation metrics."""
    root = Path(vault_path).expanduser() if vault_path is not None else None
    if current_only:
        pages: list[Entity] = []
        for entity_type in ENTITY_TYPES:
            pages.extend(list_current_entities(entity_type, vault_path=root))
    else:
        pages = _all_pages(root)
    return calculate_relation_metrics(pages)


def format_relation_metrics_lines(metrics: dict[str, MetricValue]) -> tuple[str, ...]:
    """Render doctor-friendly relation metric lines."""
    total = int(metrics["total_pages"])
    typed_pages = int(metrics["typed_relation_pages"])
    legacy_count = int(metrics["legacy_related_residual_count"])
    orphan_pages = int(metrics["orphan_pages"])
    return (
        "typed_relation_coverage: "
        f"{_format_percent(float(metrics['typed_relation_coverage']))} "
        f"({typed_pages}/{total})",
        "legacy_related_residual: "
        f"{legacy_count} ({_format_percent(float(metrics['legacy_related_residual_ratio']))})",
        f"orphan_ratio: {_format_percent(float(metrics['orphan_ratio']))} ({orphan_pages}/{total})",
    )


def _has_typed_relation(entity: Entity) -> bool:
    return any(_has_values(getattr(entity, relation)) for relation in RELATION_FIELDS)


def _has_related(entity: Entity) -> bool:
    return _has_values(entity.related)


def _has_values(values: Iterable[object]) -> bool:
    return any(str(value).strip() for value in values)


def _ratio(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


def _format_percent(ratio: float) -> str:
    return f"{ratio * 100:.1f}%"
