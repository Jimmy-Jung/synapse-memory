"""Relation coverage metrics.

Author: JunyoungJung
Created: 2026-07-07
"""

from __future__ import annotations

import pytest

from synapse_memory.model import Entity
from synapse_memory.wiki.metrics import calculate_relation_metrics


def test_relation_metrics_empty_pages() -> None:
    metrics = calculate_relation_metrics([])

    assert metrics["total_pages"] == 0
    assert metrics["typed_relation_coverage"] == 0
    assert metrics["legacy_related_residual_count"] == 0
    assert metrics["legacy_related_residual_ratio"] == 0
    assert metrics["orphan_pages"] == 0
    assert metrics["orphan_ratio"] == 0


def test_relation_metrics_all_orphan() -> None:
    pages = [
        Entity(type="concept", slug="rag", title="RAG"),
        Entity(type="project", slug="synapse-memory", title="Synapse Memory"),
    ]

    metrics = calculate_relation_metrics(pages)

    assert metrics["typed_relation_pages"] == 0
    assert metrics["typed_relation_coverage"] == 0
    assert metrics["legacy_related_residual_count"] == 0
    assert metrics["legacy_related_residual_ratio"] == 0
    assert metrics["orphan_pages"] == 2
    assert metrics["orphan_ratio"] == 1


def test_relation_metrics_all_typed() -> None:
    pages = [
        Entity(type="project", slug="synapse-memory", title="Synapse Memory", uses=("rag",)),
        Entity(type="insight", slug="decision", title="Decision", decided_in=("log-1",)),
    ]

    metrics = calculate_relation_metrics(pages)

    assert metrics["typed_relation_pages"] == 2
    assert metrics["typed_relation_coverage"] == 1
    assert metrics["legacy_related_residual_count"] == 0
    assert metrics["legacy_related_residual_ratio"] == 0
    assert metrics["orphan_pages"] == 0
    assert metrics["orphan_ratio"] == 0


def test_relation_metrics_mixed_related_only_residual() -> None:
    pages = [
        Entity(type="project", slug="typed", title="Typed", uses=("rag",)),
        Entity(type="concept", slug="legacy", title="Legacy", related=("[[rag]]",)),
        Entity(type="concept", slug="orphan", title="Orphan"),
    ]

    metrics = calculate_relation_metrics(pages)

    assert metrics["total_pages"] == 3
    assert metrics["typed_relation_pages"] == 1
    assert metrics["typed_relation_coverage"] == pytest.approx(1 / 3)
    assert metrics["legacy_related_residual_count"] == 1
    assert metrics["legacy_related_residual_ratio"] == pytest.approx(1 / 3)
    assert metrics["orphan_pages"] == 1
    assert metrics["orphan_ratio"] == pytest.approx(1 / 3)
