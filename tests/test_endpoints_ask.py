"""ask endpoint 테스트 — RAG/Claude mock.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import synapse_memory.endpoints.ask as ask_mod
from synapse_memory.endpoints.ask import (
    AskResult,
    SourceCitation,
    _build_context,
    ask,
)
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.rag.vector_store import VectorRecord


def _claude_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.x",
        model="sonnet",
    )


def _mock_record(card_id: str, kind: str, name: str, doc: str) -> VectorRecord:
    return VectorRecord(
        id=f"{kind}:{card_id}",
        document=doc,
        embedding=[0.0],
        metadata={
            "source_kind": kind,
            "card_id": card_id,
            "display_name": name,
        },
    )


class TestBuildContext:
    def test_includes_all_sources(self) -> None:
        results = [
            (_mock_record("dansim", "card_project", "단심", "# 단심\n## 문제\n..."), 0.4),
            (_mock_record("danggeun", "card_company", "당근", "# 당근\n..."), 0.5),
        ]
        ctx = _build_context(results)
        assert "[dansim]" in ctx
        assert "[danggeun]" in ctx
        assert "card_project" in ctx
        assert "card_company" in ctx
        assert "단심" in ctx


class TestAsk:
    def _setup_store(self, records: list[tuple]) -> MagicMock:
        store = MagicMock()
        store.query.return_value = records
        return store

    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError):
            ask("", store=MagicMock())

    def test_no_results_returns_helpful_message(self) -> None:
        store = self._setup_store([])
        with patch.object(ask_mod, "embed_query", return_value=[0.0]):
            result = ask("질문", store=store, claude_env=_claude_env())
        assert "rag index" in result.answer.lower()
        assert result.sources == []

    def test_returns_answer_and_sources(self) -> None:
        records = [
            (_mock_record("dansim", "card_project", "단심", "# 단심"), 0.4),
            (_mock_record("danggeun", "card_company", "당근", "# 당근"), 0.5),
        ]
        store = self._setup_store(records)
        with patch.object(
            ask_mod, "embed_query", return_value=[0.0]
        ), patch.object(
            ask_mod.claude_api,
            "complete",
            return_value="당신은 단심앱을 만들었습니다 [dansim].",
        ):
            result = ask("뭐 만들었어?", store=store, claude_env=_claude_env())

        assert "단심앱" in result.answer
        assert len(result.sources) == 2
        assert result.sources[0].card_id == "dansim"
        assert result.sources[0].source_kind == "card_project"

    def test_passes_where_filter(self) -> None:
        store = self._setup_store([])
        with patch.object(ask_mod, "embed_query", return_value=[0.0]):
            ask(
                "q",
                store=store,
                claude_env=_claude_env(),
                where={"source_kind": "card_project"},
            )
        kwargs = store.query.call_args.kwargs
        assert kwargs["where"] == {"source_kind": "card_project"}

    def test_top_k_passed(self) -> None:
        store = self._setup_store([])
        with patch.object(ask_mod, "embed_query", return_value=[0.0]):
            ask("q", top_k=10, store=store, claude_env=_claude_env())
        assert store.query.call_args.kwargs["top_k"] == 10

    def test_claude_receives_context(self) -> None:
        records = [
            (_mock_record("x", "card_project", "X", "# X 내용 풍부"), 0.3),
        ]
        store = self._setup_store(records)
        with patch.object(
            ask_mod, "embed_query", return_value=[0.0]
        ), patch.object(
            ask_mod.claude_api, "complete", return_value="답변"
        ) as mock_complete:
            ask("문의", store=store, claude_env=_claude_env())

        prompt = mock_complete.call_args.args[0]
        assert "문의" in prompt
        assert "[x]" in prompt
        assert "X 내용 풍부" in prompt
