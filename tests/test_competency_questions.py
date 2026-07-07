"""Competency question baseline for ontology completion Step 1.

Author: JunyoungJung
Created: 2026-07-07
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import synapse_memory.wiki.query as wiki_query
from synapse_memory.model import (
    RELATION_FIELDS,
    Entity,
    fields_for,
    load_schema,
    supersedes_history,
)
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
        pytest.param("CQ10", marks=pytest.mark.xfail(reason="edge provenance는 후속 provenance 확장 대상", strict=True)),
        pytest.param("CQ11", marks=pytest.mark.xfail(reason="관계 타입별 grouping retrieval은 Step 3 대상", strict=True)),
        pytest.param("CQ12", marks=pytest.mark.xfail(reason="episodic/semantic 분리 검색은 후속 retrieval 대상", strict=True)),
        pytest.param("CQ13", marks=pytest.mark.xfail(reason="supersedes 감사 조회는 Step 5 대상", strict=True)),
        pytest.param("CQ14", marks=pytest.mark.xfail(reason="반복 log 승격은 후속 semantic promotion 대상", strict=True)),
    ],
)
def test_xfail_competency_questions_are_tracked(
    cq_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_future_competency_question(cq_id, tmp_path, monkeypatch)


def _assert_future_competency_question(
    cq_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    elif cq_id == "CQ02":
        assert "t_invalid" in fields_for("company")
        target = Entity(
            type="company",
            slug="acme-target",
            title="Acme target",
            status="target",
            attrs={"t_invalid": "2026-07-07"},
        )
        hired = Entity(
            type="company",
            slug="acme-hired",
            title="Acme hired",
            status="hired",
            supersedes=("company:acme-target",),
        )
        history = supersedes_history([target, hired], "company:acme-hired")
        assert [company.status for company in history] == ["hired", "target"]
        assert history[1].t_invalid == "2026-07-07"
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
    elif cq_id == "CQ07":
        from synapse_memory.store import save_page

        old = Entity(
            type="insight",
            slug="stance-v1",
            title="Swift concurrency stance v1",
            status="superseded",
            created="2026-01-01T09:00:00+09:00",
            observed_at="2026-01-01T09:00:00+09:00",
        )
        current = Entity(
            type="insight",
            slug="stance-v2",
            title="Swift concurrency stance v2",
            created="2026-07-01T09:00:00+09:00",
            observed_at="2026-07-01T09:00:00+09:00",
            supersedes=("insight:stance-v1",),
        )
        save_page(old, vault_path=tmp_path)
        save_page(current, vault_path=tmp_path)

        def fake_retrieve_items(*args: object, **kwargs: object) -> list[Entity]:
            all_pages = args[1]
            return [page for page in all_pages if page.slug == "stance-v2"]

        def fake_complete(prompt: str, *args: object, **kwargs: object) -> str:
            if "[[stance-v1]]" in prompt:
                return "초기 입장은 v1입니다 [[stance-v1]] 현재 입장은 v2입니다 [[stance-v2]]"
            return "현재 입장은 v2입니다 [[stance-v2]]"

        monkeypatch.setattr(wiki_query, "retrieve_items", fake_retrieve_items)
        monkeypatch.setattr(wiki_query.ai_api, "complete", fake_complete)

        answer = wiki_query.ask_wiki("Swift concurrency stance 시간순 변화", vault_path=tmp_path)
        assert answer.sources == ["stance-v1", "stance-v2"]
    elif cq_id == "CQ08":
        pages = [
            Entity(type="concept", slug="swift-concurrency-alias", title="swift concurrency alias", same_as=("swift-concurrency",)),
            Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency"),
        ]
        hits = find_related_pages("Swift Concurrency 중복 concept", max_pages=10, semantic_fn=None, pages=pages)
        assert "swift-concurrency-alias" in {page.slug for page in hits}
    elif cq_id == "CQ09":
        assert "kind" in fields_for("concept")
    elif cq_id == "CQ10":
        uses_spec = load_schema()["relations"]["uses"]
        assert "provenance" in uses_spec
    elif cq_id == "CQ11":
        from synapse_memory.wiki.links import typed_neighbors

        page = Entity(
            type="project",
            slug="synapse-memory",
            title="Synapse Memory",
            related=("[[legacy-rag]]",),
            uses=("rag",),
            part_of=("memory-tools",),
        )
        neighbors = typed_neighbors(page)
        assert neighbors == {
            "uses": ("rag",),
            "part_of": ("memory-tools",),
        }
    elif cq_id == "CQ12":
        pages = [
            Entity(type="log", slug="rag-log", title="RAG"),
            Entity(type="concept", slug="rag-concept", title="RAG"),
        ]
        hits = find_related_pages("RAG", max_pages=10, semantic_fn=None, pages=pages)
        assert {page.type for page in hits} <= {"concept", "insight"}
    elif cq_id == "CQ13":
        from synapse_memory.store import load_page, save_page
        from synapse_memory.wiki.apply import apply_ops
        from synapse_memory.wiki.integration import PageOp

        save_page(
            Entity(type="company", slug="acme-v1", title="Acme", status="target"),
            vault_path=tmp_path,
        )
        apply_ops(
            [
                PageOp(
                    op="create",
                    page=Entity(
                        type="company",
                        slug="acme-v2",
                        title="Acme",
                        status="hired",
                        supersedes=("company:acme-v1",),
                    ),
                )
            ],
            vault_path=tmp_path,
            today="2026-07-07",
        )

        invalidated = load_page("company", "acme-v1", vault_path=tmp_path)
        assert invalidated.status == "superseded"
        assert invalidated.t_invalid == "2026-07-07"
    elif cq_id == "CQ14":
        from synapse_memory.wiki.promotion import promotion_candidates_from_logs

        logs = [
            Entity(type="log", slug="log-1", title="Pytest flake", body="pytest flake repeated"),
            Entity(type="log", slug="log-2", title="Pytest flake", body="pytest flake repeated"),
        ]
        candidates = promotion_candidates_from_logs(logs, min_count=2)
        assert any(candidate.type == "insight" and "pytest" in candidate.body for candidate in candidates)
    else:
        raise AssertionError(f"unknown CQ: {cq_id}")
