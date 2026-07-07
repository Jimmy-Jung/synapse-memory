# tests/test_wiki_retrieval.py
"""find_related_pages: 이름매칭 + 1-hop 링크 확장.

020: 기본 semantic은 provider LLM 호출이므로, 이름매칭/1-hop만 검증하는 이 테스트는
``semantic_fn=None``으로 의미선별을 꺼서 hermetic하게 유지한다.
"""
from __future__ import annotations

from pathlib import Path

import synapse_memory.wiki.retrieval as retrieval_mod
from synapse_memory.model import Entity
from synapse_memory.wiki.links import reverse_relations, typed_neighbors
from synapse_memory.wiki.page import save_page
from synapse_memory.wiki.retrieval import find_related_pages


def test_typed_neighbors_groups_targets_by_relation() -> None:
    page = Entity(
        type="project",
        slug="synapse-memory",
        title="Synapse Memory",
        related=("[[legacy-rag]]",),
        uses=("rag",),
        part_of=("memory-tools",),
    )

    assert typed_neighbors(page) == {
        "uses": ("rag",),
        "part_of": ("memory-tools",),
    }


def test_reverse_relations_indexes_typed_edges_by_target() -> None:
    pages = [
        Entity(type="project", slug="async-project", title="Async Project", uses=("swift-concurrency",)),
        Entity(type="insight", slug="decision-note", title="Decision", decided_in=("daily-log",)),
    ]

    assert reverse_relations(pages) == {
        "swift-concurrency": [("uses", "async-project")],
        "daily-log": [("decided_in", "decision-note")],
    }


def test_name_match_by_title_and_slug(tmp_path: Path) -> None:
    save_page(Entity(type="project", slug="synapse-memory", title="Synapse Memory"), vault_path=tmp_path)
    save_page(Entity(type="company", slug="acme", title="Acme Corp"), vault_path=tmp_path)
    hits = find_related_pages("오늘 Synapse Memory 작업했다", vault_path=tmp_path, max_pages=10, semantic_fn=None)
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "acme" not in slugs


def test_one_hop_link_expansion(tmp_path: Path) -> None:
    save_page(Entity(type="project", slug="synapse-memory", title="Synapse Memory",
                       related=("[[rag]]",)), vault_path=tmp_path)
    save_page(Entity(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    hits = find_related_pages("Synapse Memory 진행", vault_path=tmp_path, max_pages=10, semantic_fn=None)
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "rag" in slugs


def test_one_hop_typed_relation_expansion(tmp_path: Path) -> None:
    save_page(
        Entity(
            type="project",
            slug="synapse-memory",
            title="Synapse Memory",
            uses=("rag",),
        ),
        vault_path=tmp_path,
    )
    save_page(Entity(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    hits = find_related_pages(
        "Synapse Memory 진행",
        vault_path=tmp_path,
        max_pages=10,
        semantic_fn=None,
    )
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "rag" in slugs


def test_reverse_uses_relation_expansion(tmp_path: Path) -> None:
    save_page(
        Entity(
            type="project",
            slug="async-project",
            title="Async Project",
            uses=("swift-concurrency",),
        ),
        vault_path=tmp_path,
    )
    save_page(
        Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency"),
        vault_path=tmp_path,
    )

    hits = find_related_pages(
        "Swift Concurrency를 uses하는 project",
        vault_path=tmp_path,
        max_pages=10,
        semantic_fn=None,
    )

    assert [page.slug for page in hits] == ["swift-concurrency", "async-project"]


def test_reverse_expansion_ignores_uses_substrings_and_skips_reverse_index(
    monkeypatch,
) -> None:
    pages = [
        Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency"),
        Entity(type="project", slug="async-project", title="Async Project", uses=("swift-concurrency",)),
    ]

    def fail_reverse_relations(pages):
        raise AssertionError("reverse index should be lazy when no relation intent exists")

    monkeypatch.setattr(retrieval_mod, "reverse_relations", fail_reverse_relations)

    hits = find_related_pages(
        "Swift Concurrency focuses overview",
        max_pages=10,
        semantic_fn=None,
        pages=pages,
    )

    assert [page.slug for page in hits] == ["swift-concurrency"]


def test_reverse_expansion_caps_sources_per_relation() -> None:
    pages = [Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency")]
    pages.extend(
        Entity(type="project", slug=f"async-project-{index}", title=f"Async Project {index}", uses=("swift-concurrency",))
        for index in range(7)
    )

    hits = find_related_pages(
        "Swift Concurrency uses project",
        max_pages=10,
        semantic_fn=None,
        pages=pages,
    )

    assert [page.slug for page in hits] == [
        "swift-concurrency",
        "async-project-0",
        "async-project-1",
        "async-project-2",
        "async-project-3",
        "async-project-4",
    ]


def test_typed_neighbors_rank_before_legacy_related(tmp_path: Path) -> None:
    save_page(
        Entity(
            type="project",
            slug="synapse-memory",
            title="Synapse Memory",
            related=("[[legacy-rag]]",),
            uses=("typed-rag",),
        ),
        vault_path=tmp_path,
    )
    save_page(Entity(type="concept", slug="typed-rag", title="Typed RAG"), vault_path=tmp_path)
    save_page(Entity(type="concept", slug="legacy-rag", title="Legacy RAG"), vault_path=tmp_path)

    hits = find_related_pages(
        "Synapse Memory",
        vault_path=tmp_path,
        max_pages=10,
        semantic_fn=None,
    )

    assert [page.slug for page in hits] == ["synapse-memory", "typed-rag", "legacy-rag"]


def test_respects_max_pages(tmp_path: Path) -> None:
    for i in range(5):
        save_page(Entity(type="concept", slug=f"c{i}", title=f"Concept{i}"), vault_path=tmp_path)
    text = " ".join(f"Concept{i}" for i in range(5))
    hits = find_related_pages(text, vault_path=tmp_path, max_pages=2, semantic_fn=None)
    assert len(hits) == 2


def test_no_match_returns_empty(tmp_path: Path) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    assert find_related_pages("관련 없는 내용", vault_path=tmp_path, semantic_fn=None) == []
