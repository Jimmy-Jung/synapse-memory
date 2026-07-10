"""wiki-first ask + 인용 + insight write-back (_retrieve_wiki/LLM 주입)."""
from __future__ import annotations

import datetime
from pathlib import Path  # noqa: F401
from types import SimpleNamespace

import synapse_memory.wiki.query as q
from synapse_memory.model import Entity
from synapse_memory.wiki.page import load_page, save_page


def test_ask_wiki_synthesizes_with_citation(tmp_path, monkeypatch) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG", body="검색 증강 생성"), vault_path=tmp_path)
    monkeypatch.setattr(q, "_retrieve_wiki",
        lambda query, *, vault_path, top_k, include_history=False: [load_page("concept", "rag", vault_path=vault_path)])
    monkeypatch.setattr(q.ai_api, "complete", lambda *a, **k: "RAG는 검색 증강 생성입니다 [[rag]]")
    res = q.ask_wiki("RAG가 뭐야?", vault_path=tmp_path)
    assert "RAG" in res.answer
    assert "rag" in res.sources


def test_ask_wiki_writeback_creates_insight(tmp_path, monkeypatch) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG", body="x"), vault_path=tmp_path)
    monkeypatch.setattr(q, "_retrieve_wiki",
        lambda query, *, vault_path, top_k, include_history=False: [load_page("concept", "rag", vault_path=vault_path)])
    monkeypatch.setattr(q.ai_api, "complete", lambda *a, **k: "답변 본문 [[rag]]")
    res = q.ask_wiki("RAG 설명", vault_path=tmp_path, save=True, today="2026-06-14")
    assert res.saved_slug is not None
    insight = load_page("insight", res.saved_slug, vault_path=tmp_path, when=datetime.date(2026, 6, 14))
    assert "답변 본문" in insight.body


def test_ask_wiki_no_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(q, "_retrieve_wiki", lambda query, *, vault_path, top_k, include_history=False: [])
    res = q.ask_wiki("아무거나", vault_path=tmp_path)
    assert res.sources == []
    assert "없" in res.answer  # "자료에 없음"


def test_retrieve_wiki_expands_provider_seed_typed_neighbors(tmp_path, monkeypatch) -> None:
    save_page(
        Entity(type="project", slug="synapse-memory", title="Synapse Memory", uses=("rag",)),
        vault_path=tmp_path,
    )
    save_page(Entity(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)

    monkeypatch.setattr(
        q,
        "retrieve_items",
        lambda *args, **kwargs: [load_page("project", "synapse-memory", vault_path=tmp_path)],
    )

    hits = q._retrieve_wiki("Synapse Memory", vault_path=tmp_path, top_k=5)

    assert [page.slug for page in hits] == ["synapse-memory", "rag"]


def test_retrieve_wiki_expands_provider_seed_reverse_uses(tmp_path, monkeypatch) -> None:
    save_page(
        Entity(type="project", slug="async-project", title="Async Project", uses=("swift-concurrency",)),
        vault_path=tmp_path,
    )
    save_page(
        Entity(type="concept", slug="swift-concurrency", title="Swift Concurrency"),
        vault_path=tmp_path,
    )

    monkeypatch.setattr(
        q,
        "retrieve_items",
        lambda *args, **kwargs: [load_page("concept", "swift-concurrency", vault_path=tmp_path)],
    )

    hits = q._retrieve_wiki(
        "Swift Concurrency를 uses하는 project",
        vault_path=tmp_path,
        top_k=5,
    )

    assert [page.slug for page in hits] == ["swift-concurrency", "async-project"]


def test_ask_wiki_uses_injected_environment_for_retrieval_and_ask_model(
    tmp_path, monkeypatch
) -> None:
    page = Entity(type="concept", slug="rag", title="RAG", body="검색 증강 생성")
    save_page(page, vault_path=tmp_path)
    env = SimpleNamespace(provider="claude", model="sonnet")
    captured: dict[str, object] = {}

    def fake_retrieve_items(*_args: object, **kwargs: object) -> list[Entity]:
        captured["env"] = kwargs.get("env")
        return [page]

    def fake_resolve_model(task: str, *, provider: str | None = None) -> str:
        captured["task"] = task
        captured["provider"] = provider
        return "claude-opus"

    def fake_complete(*_args: object, model: str | None = None, env: object = None, **_kwargs: object) -> str:
        captured["model"] = model
        captured["complete_env"] = env
        return "답변 [[rag]]"

    monkeypatch.setattr(q, "retrieve_items", fake_retrieve_items)
    monkeypatch.setattr(q.ai_api, "resolve_model_for_task", fake_resolve_model)
    monkeypatch.setattr(q.ai_api, "complete", fake_complete)

    q.ask_wiki("RAG가 뭐야?", vault_path=tmp_path, ai_env=env)

    assert captured == {
        "env": env,
        "task": "ask",
        "provider": "claude",
        "model": "claude-opus",
        "complete_env": env,
    }
