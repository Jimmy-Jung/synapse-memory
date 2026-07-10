"""ask endpoint 테스트 — builtin recipe adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import synapse_memory.endpoints.ask as ask_mod
from synapse_memory.endpoints.ask import ask
from synapse_memory.feedback.last_response import (
    AnswerCitation,
    load_last_answer,
    new_answer_reference,
)
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.recipes.recipe import GenerationResult
from synapse_memory.storage.l0 import L0_ENV_VAR


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.x",
        model="sonnet",
    )


def _result(answer: str = "답변 [dansim].", *card_ids: str) -> GenerationResult:
    citations = tuple(
        AnswerCitation(
            target_kind="card",
            target_ref=card_id,
            source_kind="card_project",
            display_name=card_id,
        )
        for card_id in (card_ids or ("dansim",))
    )
    return GenerationResult(
        recipe_name="ask",
        answer_markdown=answer,
        saved_path=None,
        source_ids=[c.target_ref for c in citations],
        last_answer_ref=new_answer_reference(
            command="persona.generate.ask",
            query="질문",
            citations=citations,
        ),
    )


class TestAsk:
    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError):
            ask("")

    def test_no_selection_returns_helpful_message(self) -> None:
        no_match = GenerationResult(
            recipe_name="ask",
            answer_markdown="",
            saved_path=None,
            source_ids=[],
            last_answer_ref=None,
        )
        with patch.object(ask_mod, "recipes_generate", return_value=no_match):
            result = ask("질문", ai_env=_ai_env())
        assert "Entity" in result.answer
        assert result.sources == []

    def test_returns_answer_and_sources(self) -> None:
        with patch.object(
            ask_mod,
            "recipes_generate",
            return_value=_result("단심앱을 만들었습니다 [dansim].", "dansim", "danggeun"),
        ):
            result = ask("뭐 만들었어?", ai_env=_ai_env())

        assert "단심앱" in result.answer
        assert len(result.sources) == 2
        assert result.sources[0].card_id == "dansim"
        assert result.sources[0].source_kind == "card_project"

    def test_records_last_answer_reference(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        with patch.object(ask_mod, "recipes_generate", return_value=_result()):
            ask("뭐 만들었어?", ai_env=_ai_env())

        ref = load_last_answer()
        assert ref is not None
        assert ref.command == "ask"
        assert ref.citations[0].target_ref == "dansim"

    def test_save_writes_insight_and_returns_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SYNAPSE_OBSIDIAN_VAULT", str(tmp_path / "vault"))
        with patch.object(
            ask_mod,
            "recipes_generate",
            return_value=_result(
                "개인 연락처 010-1234-5678 대신 단심 근거 [dansim].",
                "dansim",
            ),
        ):
            result = ask("TCA를 왜 도입했지?", ai_env=_ai_env(), save=True)

        assert result.saved_path is not None
        text = result.saved_path.read_text(encoding="utf-8")
        assert "010-1234-5678" in text
        assert "related:" in text
        assert "dansim" in text

    def test_save_uses_raw_question_for_frontmatter_filename(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SYNAPSE_OBSIDIAN_VAULT", str(tmp_path / "vault"))
        with patch.object(ask_mod, "recipes_generate", return_value=_result()):
            result = ask("홍길동 이직 전략", ai_env=_ai_env(), save=True)

        assert result.saved_path is not None
        assert "홍길동" in result.saved_path.name
        text = result.saved_path.read_text(encoding="utf-8")
        assert "홍길동 이직 전략" in text

    def test_passes_query_to_builtin_recipe(self) -> None:
        with patch.object(
            ask_mod, "recipes_generate", return_value=_result("단심앱입니다 [dansim].")
        ) as mock_generate:
            result = ask("뭐 만들었어?", ai_env=_ai_env())

        assert result.answer == "단심앱입니다 [dansim]."
        assert mock_generate.call_args.args == ("ask",)
        assert mock_generate.call_args.kwargs["inputs"] == {"query": "뭐 만들었어?"}

    def test_default_model_uses_provider_task_route(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ask_mod,
            "resolve_model_for_task",
            lambda task, **_kwargs: "gpt-5.6-sol" if task == "ask" else None,
            raising=False,
        )
        with patch.object(ask_mod, "recipes_generate", return_value=_result()) as generate:
            ask("q", ai_env=SimpleNamespace(provider="codex", model="gpt-5.6-terra"))

        assert generate.call_args.kwargs["model_override"] == "gpt-5.6-sol"

    def test_explicit_model_wins_over_provider_task_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_mod,
            "resolve_model_for_task",
            lambda *_args, **_kwargs: "gpt-5.6-sol",
            raising=False,
        )
        with patch.object(ask_mod, "recipes_generate", return_value=_result()) as generate:
            ask("q", model="custom-model", ai_env=_ai_env())

        assert generate.call_args.kwargs["model_override"] == "custom-model"

    def test_where_filter_restricts_recipe_rag_filter(self) -> None:
        with patch.object(
            ask_mod, "recipes_generate", return_value=_result()
        ) as mock_generate:
            ask("q", ai_env=_ai_env(), where={"source_kind": "card_project"})
        assert mock_generate.call_args.kwargs["rag_filter_override"] == {
            "source_kind": "card_project"
        }

    def test_top_k_passed_to_recipe(self) -> None:
        with patch.object(
            ask_mod, "recipes_generate", return_value=_result()
        ) as mock_generate:
            ask("q", top_k=10, ai_env=_ai_env())
        assert mock_generate.call_args.kwargs["top_k_override"] == 10

    def test_disables_recipe_file_save_and_last_answer_save(self) -> None:
        with patch.object(
            ask_mod, "recipes_generate", return_value=_result()
        ) as mock_generate:
            ask("문의", ai_env=_ai_env())

        assert mock_generate.call_args.kwargs["disable_save"] is True
        assert mock_generate.call_args.kwargs["save_last"] is False
