"""find_related_pages 의미 top-k 병합 (semantic_fn 주입)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from synapse_memory.model import Entity
from synapse_memory.wiki import retrieval as retrieval_mod
from synapse_memory.wiki.page import save_page
from synapse_memory.wiki.retrieval import find_related_pages


def test_semantic_retriever_adds_pages(tmp_path: Path) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG", body="검색 증강 생성"), vault_path=tmp_path)
    def fake_semantic(text, *, vault_path, top_k):
        return ["rag"]
    hits = find_related_pages("임베딩 기반 문서 검색", vault_path=tmp_path, semantic_fn=fake_semantic)
    assert "rag" in {p.slug for p in hits}


def test_semantic_none_uses_name_match_only(tmp_path: Path) -> None:
    save_page(Entity(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    hits = find_related_pages("RAG 작업", vault_path=tmp_path, semantic_fn=None)
    assert "rag" in {p.slug for p in hits}


def test_default_semantic_retrieval_forwards_injected_ai_environment(monkeypatch) -> None:
    """기본 provider semantic 경로는 select_related까지 주입 env를 전달한다."""
    env = SimpleNamespace(provider="claude", model="sonnet")
    captured: dict[str, object] = {}
    pages = [Entity(type="concept", slug="rag", title="RAG")]

    def fake_retrieve(*_args, **kwargs):
        captured["env"] = kwargs.get("env")
        return []

    monkeypatch.setattr(retrieval_mod, "retrieve_items", fake_retrieve)

    assert find_related_pages("검색", pages=pages, ai_env=env) == []
    assert captured["env"] is env
