"""Entity temporal model tests.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from datetime import datetime

from synapse_memory.cards.card_index import build_card_index
from synapse_memory.cards.project import ProjectCard, save_project_card
from synapse_memory.model import (
    Entity,
    backfill_created,
    current_entities,
    parse_entity,
    serialize_entity,
    supersedes_history,
)


def test_new_entity_records_created() -> None:
    entity = Entity(slug="temporal-test", title="Temporal Test", type="concept")

    datetime.fromisoformat(entity.created)

    restored = parse_entity(serialize_entity(entity))

    assert restored.created == entity.created


def test_observed_at_is_insight_log_only() -> None:
    insight = Entity(
        slug="position-now",
        title="현재 입장",
        type="insight",
        attrs={"question": "입장?", "command": "recall"},
    )
    concept = Entity(
        slug="plain-concept",
        title="Plain Concept",
        type="concept",
        observed_at="2026-07-06T10:00:00+09:00",
    )

    assert insight.observed_at == insight.created
    assert "observed_at:" in serialize_entity(insight)
    assert "observed_at:" not in serialize_entity(concept)


def test_backfill_created_uses_recorded_at_before_source_timestamp() -> None:
    entity = parse_entity(
        "---\n"
        "type: concept\n"
        "slug: old-position\n"
        "title: 예전 입장\n"
        "sources:\n"
        "  - timestamp: 2026-06-01T09:00:00+09:00\n"
        "---\n"
        "body"
    )

    restored = backfill_created(entity, recorded_at="2026-05-30T08:00:00+09:00")

    assert entity.created == ""
    assert restored.created == "2026-05-30T08:00:00+09:00"


def test_supersedes_history_builds_position_change_chain() -> None:
    old = Entity(
        slug="stance-v1",
        title="초기 입장",
        type="insight",
        status="superseded",
        created="2026-01-01T09:00:00+09:00",
        observed_at="2026-01-01T09:00:00+09:00",
        attrs={"question": "X 입장?", "command": "recall"},
    )
    middle = Entity(
        slug="stance-v2",
        title="중간 입장",
        type="insight",
        status="superseded",
        created="2026-03-01T09:00:00+09:00",
        observed_at="2026-03-01T09:00:00+09:00",
        supersedes=("insight:stance-v1",),
        attrs={"question": "X 입장?", "command": "recall"},
    )
    current = Entity(
        slug="stance-v3",
        title="현재 입장",
        type="insight",
        created="2026-07-01T09:00:00+09:00",
        observed_at="2026-07-01T09:00:00+09:00",
        supersedes=("insight:stance-v2",),
        attrs={"question": "X 입장?", "command": "recall"},
    )

    history = supersedes_history([old, current, middle], "insight:stance-v3")

    assert [entity.slug for entity in history] == ["stance-v3", "stance-v2", "stance-v1"]
    assert [entity.slug for entity in current_entities(history)] == ["stance-v3"]


def test_superseded_entity_is_filtered_from_current_card_index(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    save_project_card(
        ProjectCard(
            project_id="stance-v1",
            display_name="예전 입장",
            status="superseded",
            body="이전 답변",
        ),
        vault_path=vault,
    )
    save_project_card(
        ProjectCard(
            project_id="stance-v2",
            display_name="현재 입장",
            status="active",
            supersedes=["project:stance-v1"],
            body="현재 답변",
        ),
        vault_path=vault,
    )

    index = build_card_index(vault_path=vault, kinds=("project",))

    assert index.slugs == frozenset({"stance-v2"})
