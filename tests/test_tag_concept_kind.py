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


def test_scoring_picks_higher_count_not_first_match() -> None:
    # methodology 1건(process) vs tool 3건(cli/sdk/도구). first-match(옛 로직)면
    # methodology로 새지만, 스코어링은 매칭 수가 많은 tool을 고른다.
    ent = Entity(
        type="concept",
        slug="deploy-toolkit",
        title="배포 process",
        body="cli 와 sdk 도구 모음",
    )
    assert heuristic_kind(ent) == "tool"


def test_pattern_alone_no_longer_forces_methodology() -> None:
    # "패턴"만으로 methodology 오분류하던 케이스(redux류): tool 신호가 이긴다.
    redux = Entity(
        type="concept",
        slug="redux",
        title="Redux",
        body="상태관리 라이브러리이자 단방향 데이터 흐름 패턴. React 프레임워크 도구.",
    )
    assert heuristic_kind(redux) == "tool"


def test_strong_methodology_signal_still_classifies() -> None:
    # 키워드 정리 후에도 강한 methodology 신호는 유지돼야 한다(과삭제 가드).
    tdd = Entity(
        type="concept",
        slug="tdd",
        title="TDD 방법론",
        body="테스트 주도 개발 워크플로 원칙",
    )
    assert heuristic_kind(tdd) == "methodology"
