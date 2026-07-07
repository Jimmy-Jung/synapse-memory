"""Competency question baseline for ontology completion Step 1.

Author: JunyoungJung
Created: 2026-07-07
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import synapse_memory.wiki.query as wiki_query
from synapse_memory.model import Entity, RELATION_FIELDS, fields_for
from synapse_memory.wiki.metrics import calculate_relation_metrics
from synapse_memory.wiki.retrieval import find_related_pages

CQ_PATH = Path(__file__).parents[1] / "src" / "synapse_memory" / "competency_questions.yaml"

VALID_KINDS = {
    "relational",
    "hierarchical",
    "temporal",
    "identity",
    "classification",
    "provenance",
    "coverage",
}
VALID_STATUSES = {"supported", "xfail"}
EXPECTED_SUPPORTED = {"CQ03", "CQ15"}
EXPECTED_XFAIL = {
    "CQ01",
    "CQ02",
    "CQ04",
    "CQ05",
    "CQ06",
    "CQ07",
    "CQ08",
    "CQ09",
    "CQ10",
    "CQ11",
    "CQ12",
    "CQ13",
    "CQ14",
}


def _load_competency_questions() -> list[dict[str, str]]:
    return yaml.safe_load(CQ_PATH.read_text(encoding="utf-8"))


def test_competency_questions_yaml_declares_review_backbone() -> None:
    questions = _load_competency_questions()

    assert [question["id"] for question in questions] == [f"CQ{i:02d}" for i in range(1, 16)]
    assert {question["kind"] for question in questions} <= VALID_KINDS
    assert {question["status"] for question in questions} <= VALID_STATUSES
    assert {question["id"] for question in questions if question["status"] == "supported"} == EXPECTED_SUPPORTED
    assert {question["id"] for question in questions if question["status"] == "xfail"} == EXPECTED_XFAIL
    assert all(question["question"] for question in questions)


def test_supported_cq03_decided_in_relation_is_retrievable() -> None:
    pages = [
        Entity(
            type="insight",
            slug="provider-only-decision",
            title="Provider-only decision",
            decided_in=("log-2026-07-07",),
        ),
        Entity(type="log", slug="log-2026-07-07", title="2026-07-07 implementation log"),
    ]

    hits = find_related_pages(
        "Provider-only decision",
        max_pages=10,
        semantic_fn=None,
        pages=pages,
    )

    assert [page.slug for page in hits] == ["provider-only-decision", "log-2026-07-07"]


def test_supported_cq03_ask_wiki_can_answer_from_retrieved_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        Entity(type="insight", slug="provider-only-decision", title="Provider-only decision"),
        Entity(type="log", slug="log-2026-07-07", title="2026-07-07 implementation log"),
    ]
    monkeypatch.setattr(wiki_query, "_retrieve_wiki", lambda query, *, vault_path, top_k: pages)
    monkeypatch.setattr(
        wiki_query.ai_api,
        "complete",
        lambda *args, **kwargs: "이 decision은 log에 근거가 있습니다 [[log-2026-07-07]]",
    )

    answer = wiki_query.ask_wiki("이 decision이 decided_in된 log는?", vault_path=None)

    assert answer.sources == ["log-2026-07-07"]


def test_supported_cq15_orphan_pages_are_measurable() -> None:
    pages = [
        Entity(type="project", slug="typed", title="Typed", uses=("rag",)),
        Entity(type="concept", slug="legacy", title="Legacy", related=("[[rag]]",)),
        Entity(type="concept", slug="orphan", title="Orphan"),
    ]

    metrics = calculate_relation_metrics(pages)

    assert metrics["orphan_pages"] == 1
    assert metrics["orphan_ratio"] == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "cq_id",
    [
        pytest.param("CQ01", marks=pytest.mark.xfail(reason="uses 역방향 조회는 Step 3 역인덱스 대상", strict=True)),
        pytest.param("CQ02", marks=pytest.mark.xfail(reason="company status valid-time 이력은 Step 5 대상", strict=True)),
        pytest.param("CQ04", marks=pytest.mark.xfail(reason="broader/narrower 계층 관계는 Step 7 게이트 대상", strict=True)),
        pytest.param("CQ05", marks=pytest.mark.xfail(reason="part_of transitive closure는 Step 7 대상", strict=True)),
        pytest.param("CQ06", marks=pytest.mark.xfail(reason="t_invalid active filter는 Step 5 대상", strict=True)),
        pytest.param("CQ07", marks=pytest.mark.xfail(reason="supersedes recall 배선은 Step 5 대상", strict=True)),
        pytest.param("CQ08", marks=pytest.mark.xfail(reason="same_as entity-resolution은 Step 7 대상", strict=True)),
        pytest.param("CQ09", marks=pytest.mark.xfail(reason="concept.kind 분류는 Step 6 대상", strict=True)),
        pytest.param("CQ10", marks=pytest.mark.xfail(reason="edge provenance는 후속 온톨로지 확장 대상", strict=True)),
        pytest.param("CQ11", marks=pytest.mark.xfail(reason="관계 타입별 grouping retrieval은 Step 3 대상", strict=True)),
        pytest.param("CQ12", marks=pytest.mark.xfail(reason="episodic/semantic 분리 검색은 후속 retrieval 대상", strict=True)),
        pytest.param("CQ13", marks=pytest.mark.xfail(reason="supersedes 감사 조회는 Step 5 대상", strict=True)),
        pytest.param("CQ14", marks=pytest.mark.xfail(reason="log 패턴 승격은 후속 semantic promotion 대상", strict=True)),
    ],
)
def test_xfail_competency_questions_are_tracked(cq_id: str) -> None:
    _assert_future_competency_question(cq_id)


def _assert_future_competency_question(cq_id: str) -> None:
    if cq_id == "CQ01":
        pages = [
            Entity(type="project", slug="async-project", title="Async Project", uses=("swift-concurrency",)),
            Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency"),
        ]
        hits = find_related_pages(
            "Swift Concurrency를 uses하는 project",
            max_pages=10,
            semantic_fn=None,
            pages=pages,
        )
        assert "async-project" in {page.slug for page in hits}
    elif cq_id == "CQ04":
        assert "broader" in RELATION_FIELDS
    elif cq_id == "CQ05":
        pages = [
            Entity(type="project", slug="feature", title="Feature", part_of=("product",)),
            Entity(type="project", slug="product", title="Product", part_of=("portfolio",)),
            Entity(type="project", slug="portfolio", title="Portfolio"),
        ]
        hits = find_related_pages("Feature", max_pages=10, semantic_fn=None, pages=pages)
        assert "portfolio" in {page.slug for page in hits}
    elif cq_id == "CQ06":
        pages = [Entity(type="concept", slug="old-fact", title="Old Fact", status="superseded")]
        hits = find_related_pages("Old Fact", max_pages=10, semantic_fn=None, pages=pages)
        assert not hits
    elif cq_id == "CQ08":
        pages = [
            Entity(type="concept", slug="swift-concurrency-alias", title="swift concurrency alias", same_as=("swift-concurrency",)),
            Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency"),
        ]
        hits = find_related_pages("Swift Concurrency 중복 concept", max_pages=10, semantic_fn=None, pages=pages)
        assert "swift-concurrency-alias" in {page.slug for page in hits}
    elif cq_id == "CQ09":
        assert "kind" in fields_for("concept")
    elif cq_id == "CQ12":
        pages = [
            Entity(type="log", slug="rag-log", title="RAG"),
            Entity(type="concept", slug="rag-concept", title="RAG"),
        ]
        hits = find_related_pages("RAG", max_pages=10, semantic_fn=None, pages=pages)
        assert {page.type for page in hits} <= {"concept", "insight"}
    else:
        raise AssertionError(f"{cq_id} is not supported by the current Step 1 measurement layer")
