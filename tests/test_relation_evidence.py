"""Typed edge provenance contracts.

Author: JunyoungJung
Created: 2026-09-22
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from synapse_memory.model import (
    Entity,
    RelationEvidence,
    entity_from_meta,
    normalize_relation_target,
    parse_entity,
    render_schema_guidance,
    serialize_entity,
)


def evidence(**changes: object) -> RelationEvidence:
    return RelationEvidence(**{
        "relation": "uses", "target": "concept:swift",
        "source": "codex:2026/09/session.jsonl",
        "start_byte": 10, "end_byte": 80, "start_char": 2, "end_char": 14,
        "sha256": "a" * 64, **changes,
    })


def test_evidence_is_immutable_and_roundtrips_without_raw_text() -> None:
    value = evidence(target="[[concept:swift|Swift]]")
    assert value.target == "concept:swift"
    with pytest.raises(FrozenInstanceError):
        value.target = "other"
    page = Entity(type="project", slug="app", title="App",
                  uses=("[[concept:swift|Swift]]",), relation_evidence=(value,))
    serialized = serialize_entity(page)
    restored = parse_entity(serialized)
    assert restored.relation_evidence == (value,)
    assert restored.sources == ()
    assert "relation_evidence:" in serialized
    assert "quote:" not in serialized


def test_legacy_pages_load_without_evidence() -> None:
    page = entity_from_meta({"type": "project", "slug": "app", "title": "App",
                             "uses": ["swift"]})
    assert page.relation_evidence == ()
    assert "relation_evidence:" not in serialize_entity(page)


@pytest.mark.parametrize("changes", [
    {"relation": "related"}, {"relation": "missing"},
    {"target": ""}, {"target": "../swift"}, {"target": "concept:sw\\ift"},
    {"target": "swift\n"}, {"target": 4},
    {"source": "vault-md:source.jsonl"}, {"source": "codex:/source.jsonl"},
    {"source": "codex:../source.jsonl"}, {"source": "codex:logs//source.jsonl"},
    {"source": "codex:logs/./source.jsonl"}, {"source": "codex:logs\\source.jsonl"},
    {"source": "codex:source.jsonl\n"}, {"source": "codex:source.md"},
    {"source": "codex:C:/source.jsonl"}, {"source": 8},
    {"start_byte": True}, {"end_byte": "80"}, {"start_char": 1.2},
    {"start_byte": -1}, {"end_byte": 10}, {"end_char": 2},
    {"sha256": "A" * 64}, {"sha256": "a" * 63}, {"sha256": None},
])
def test_invalid_evidence_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        evidence(**changes)


@pytest.mark.parametrize("raw", [
    None, "raw quote", {}, ["raw quote"],
    [{"relation": "uses"}], [{**asdict(evidence()), "quote": "private raw text"}],
])
def test_invalid_evidence_collection_is_rejected(raw: object) -> None:
    with pytest.raises(ValueError):
        entity_from_meta({"type": "project", "slug": "app", "title": "App",
                          "uses": ["concept:swift"], "relation_evidence": raw})


def test_evidence_requires_a_matching_typed_edge() -> None:
    for relations in ({}, {"related": ("concept:swift",)}, {"uses": ("swift",)}):
        with pytest.raises(ValueError, match="relation_evidence"):
            Entity(type="project", slug="app", title="App",
                   relation_evidence=(evidence(),), **relations)
    with pytest.raises(ValueError, match="relation_evidence"):
        Entity(type="project", slug="app", title="App", broader=("concept:swift",),
               relation_evidence=(evidence(relation="broader"),))


@pytest.mark.parametrize(("ref", "expected"), [
    ("swift", "swift"), ("[[swift|Swift]]", "swift"),
    (" [[concept:swift|Swift]] ", "concept:swift"),
])
def test_target_normalization_preserves_type(ref: str, expected: str) -> None:
    assert normalize_relation_target(ref) == expected


def test_schema_guidance_declares_evidence_contract() -> None:
    guidance = render_schema_guidance()
    assert "relation_evidence" in guidance
    assert "start_byte" in guidance and "start_char" in guidance
    assert "sha256" in guidance
