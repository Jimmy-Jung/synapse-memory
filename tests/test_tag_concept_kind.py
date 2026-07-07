"""concept.kind 백필 태깅 테스트.

저자: JunyoungJung
작성일: 2026-07-07
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.model import Entity
from synapse_memory.store import list_current_entities, save_page
from synapse_memory.wiki.concept_kind import (
    apply_kind_updates,
    heuristic_kind,
    propose_kind_updates,
)


def test_heuristic_classifies_and_abstains() -> None:
    assert heuristic_kind(Entity(type="concept", slug="solid", title="SOLID 원칙")) == "methodology"
    assert heuristic_kind(Entity(type="concept", slug="algo", title="정렬 알고리즘")) == "algorithm"
    # 근거 없으면 억지 분류 안 함
    assert heuristic_kind(Entity(type="concept", slug="mystery", title="Mystery")) is None


def test_propose_skips_tagged_and_unclassifiable() -> None:
    concepts = [
        Entity(type="concept", slug="tagged", title="정렬 알고리즘", attrs={"kind": "tool"}),
        Entity(type="concept", slug="algo", title="정렬 알고리즘"),
        Entity(type="concept", slug="mystery", title="Mystery"),
        Entity(type="project", slug="proj", title="정렬 알고리즘 프로젝트"),  # concept 아님
    ]
    updates = propose_kind_updates(concepts)
    assert [(c.slug, k) for c, k in updates] == [("algo", "algorithm")]


def test_apply_writes_and_is_idempotent(tmp_path: Path) -> None:
    save_page(Entity(type="concept", slug="algo", title="정렬 알고리즘"), vault_path=tmp_path)

    first = propose_kind_updates(list_current_entities("concept", vault_path=tmp_path))
    assert apply_kind_updates(first, vault_path=tmp_path) == ["algo"]

    reloaded = list_current_entities("concept", vault_path=tmp_path)
    assert reloaded[0].attrs.get("kind") == "algorithm"

    # 재실행: 이미 태깅됨 → 제안 없음 (idempotent)
    assert propose_kind_updates(reloaded) == []
