"""Entity model tests.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

import inspect

from synapse_memory.cards.company import CompanyCard, JobPosition, parse_company_card
from synapse_memory.cards.insight import InsightCard
from synapse_memory.cards.project import ProjectCard, ProjectMetric, parse_project_card
from synapse_memory.model import (
    ENTITY_TYPES,
    RELATION_FIELDS,
    Entity,
    load_schema,
    parse_entity,
    serialize_entity,
)


def test_schema_declares_single_entity_vocabulary_without_person() -> None:
    schema = load_schema()

    assert ENTITY_TYPES == ("project", "company", "concept", "insight", "log", "profile")
    assert "person" not in schema["types"]
    assert tuple(schema["relations"].keys()) == RELATION_FIELDS


def test_entity_round_trip_preserves_project_attrs_and_relations() -> None:
    entity = Entity(
        slug="dansim-ios",
        title="단심",
        type="project",
        status="completed",
        updated="2026-07-06",
        sources=("obsidian:10_Active/단심.md",),
        uses=("concept:swift",),
        attrs={
            "role": "iOS Lead",
            "period_start": "2023-09",
            "period_end": "2024-12",
            "domains": ["ios", "mobile"],
            "stack": ["Swift", "TCA"],
            "metrics": [
                {"name": "D7 retention", "before": "18%", "after": "31%"},
                {"name": "paid", "value": "2.1%"},
            ],
        },
        body="## 영향\n수치 개선",
    )

    restored = parse_entity(serialize_entity(entity))

    assert restored.type == "project"
    assert restored.uses == ("concept:swift",)
    assert restored.attrs["role"] == "iOS Lead"
    assert restored.attrs["period_start"] == "2023-09"
    assert restored.attrs["period_end"] == "2024-12"
    assert restored.attrs["domains"] == ["ios", "mobile"]
    assert restored.attrs["stack"] == ["Swift", "TCA"]
    assert restored.attrs["metrics"][0].before == "18%"
    assert restored.attrs["metrics"][0].after == "31%"
    assert restored.attrs["metrics"][1].value == "2.1%"


def test_v1_project_card_fields_are_preserved_in_entity_attrs() -> None:
    card = parse_project_card(
        "---\n"
        "project_id: p1\n"
        "display_name: Project One\n"
        "role: Lead\n"
        "period_start: 2026-01\n"
        "period_end: 2026-03\n"
        "domains: [ios]\n"
        "stack: [Swift]\n"
        "metrics:\n"
        "  - { name: speed, before: 2s, after: 1s }\n"
        "---\n"
        "body"
    )

    assert isinstance(card, Entity)
    assert card.slug == "p1"
    assert card.title == "Project One"
    assert card.attrs["role"] == "Lead"
    assert card.attrs["period_start"] == "2026-01"
    assert card.attrs["period_end"] == "2026-03"
    assert card.attrs["domains"] == ["ios"]
    assert card.attrs["stack"] == ["Swift"]
    assert card.attrs["metrics"][0].before == "2s"
    assert card.attrs["metrics"][0].after == "1s"


def test_v1_company_card_fields_are_preserved_in_entity_attrs() -> None:
    card = parse_company_card(
        "---\n"
        "company_id: acme\n"
        "display_name: Acme\n"
        "resume_language: en\n"
        "positions:\n"
        "  - title: Staff iOS Engineer\n"
        "    seniority: staff\n"
        "    keywords: [Swift, UIKit]\n"
        "---\n"
        "body"
    )

    assert isinstance(card, Entity)
    assert card.attrs["resume_language"] == "en"
    assert card.attrs["positions"][0].title == "Staff iOS Engineer"
    assert card.attrs["positions"][0].seniority == "staff"
    assert card.attrs["positions"][0].keywords == ["Swift", "UIKit"]


def test_card_constructor_shims_return_entity_without_extra_models() -> None:
    project = ProjectCard(
        project_id="p",
        display_name="P",
        metrics=[ProjectMetric(name="impact", value="10%")],
    )
    company = CompanyCard(
        company_id="c",
        display_name="C",
        resume_language="ko",
        positions=[JobPosition(title="Engineer")],
    )
    insight = InsightCard(
        insight_id="i",
        question="Q",
        command="ask",
        created="2026-07-06T10:00:00+09:00",
    )

    assert isinstance(project, Entity)
    assert isinstance(company, Entity)
    assert isinstance(insight, Entity)
    assert not inspect.isclass(InsightCard)


def test_legacy_domain_and_life_mapping_is_documented() -> None:
    mapping = load_schema()["legacy_mappings"]

    assert mapping["domain"]["maps_to"] == "concept"
    assert mapping["life"]["maps_to"] == "skip"
