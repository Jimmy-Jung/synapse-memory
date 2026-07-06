"""ask endpoint 테스트 — provider 선별 + Claude 합성 mock (020 provider-only).

벡터/임베딩 의존 제거. ``build_card_index``/``select_related``/``_load_card_text``/
``ai_api.complete`` 를 monkeypatch 해 hermetic 하게 검증한다. 정확한 cosine 순위
단언은 폐기 — "provider 선별 호출됨 + 합성 반환" 수준으로 본다.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import synapse_memory.endpoints.ask as ask_mod
from synapse_memory.cards.card_index import CardEntry, CardIndex
from synapse_memory.endpoints.ask import ask
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.storage.l0 import L0_ENV_VAR
from synapse_memory.storage.last_response import load_last_answer


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.x",
        model="sonnet",
    )


def _entry(card_id: str, kind: str, title: str) -> CardEntry:
    return CardEntry(
        card_id=card_id,
        kind=kind,  # type: ignore[arg-type]
        title=title,
        summary=f"{title} 요약",
        meta={
            "source_kind": f"card_{kind}",
            "display_name": title,
        },
    )


def _index(*entries: CardEntry) -> CardIndex:
    return CardIndex(entries=tuple(entries))


class TestAsk:
    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError):
            ask("")

    def test_no_selection_returns_helpful_message(self) -> None:
        with patch.object(
            ask_mod, "build_card_index", return_value=_index(_entry("x", "project", "X"))
        ), patch.object(ask_mod, "select_related", return_value=[]):
            result = ask("질문", ai_env=_ai_env())
        assert "Card" in result.answer
        assert result.sources == []

    def test_empty_index_returns_helpful_message(self) -> None:
        with patch.object(ask_mod, "build_card_index", return_value=_index()):
            result = ask("질문", ai_env=_ai_env())
        assert result.sources == []

    def test_returns_answer_and_sources(self) -> None:
        index = _index(
            _entry("dansim", "project", "단심"),
            _entry("danggeun", "company", "당근"),
        )
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=["dansim", "danggeun"]
        ), patch.object(
            ask_mod, "_load_card_text", side_effect=lambda cid, *a, **k: f"# {cid}"
        ), patch.object(
            ask_mod.ai_api,
            "complete",
            return_value="당신은 단심앱을 만들었습니다 [dansim].",
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
        index = _index(_entry("dansim", "project", "단심"))
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=["dansim"]
        ), patch.object(
            ask_mod, "_load_card_text", return_value="# 단심"
        ), patch.object(
            ask_mod.ai_api, "complete", return_value="단심앱입니다 [dansim]."
        ):
            ask("뭐 만들었어?", ai_env=_ai_env())

        ref = load_last_answer()
        assert ref is not None
        assert ref.command == "ask"
        assert ref.citations[0].target_ref == "dansim"

    def test_save_writes_insight_and_returns_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SYNAPSE_OBSIDIAN_VAULT", str(tmp_path / "vault"))
        index = _index(_entry("dansim", "project", "단심"))
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=["dansim"]
        ), patch.object(
            ask_mod, "_load_card_text", return_value="# 단심"
        ), patch.object(
            ask_mod.ai_api,
            "complete",
            return_value="개인 연락처 010-1234-5678 대신 단심 근거 [dansim].",
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
        index = _index(_entry("dansim", "project", "단심"))
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=["dansim"]
        ), patch.object(
            ask_mod, "_load_card_text", return_value="# 단심"
        ), patch.object(
            ask_mod.ai_api, "complete", return_value="답변 본문 [dansim]."
        ):
            result = ask("홍길동 이직 전략", ai_env=_ai_env(), save=True)

        assert result.saved_path is not None
        assert "홍길동" in result.saved_path.name
        text = result.saved_path.read_text(encoding="utf-8")
        assert "홍길동 이직 전략" in text

    def test_strips_claude_meta_prefix(self) -> None:
        index = _index(_entry("dansim", "project", "단심"))
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=["dansim"]
        ), patch.object(
            ask_mod, "_load_card_text", return_value="# 단심"
        ), patch.object(
            ask_mod.ai_api,
            "complete",
            return_value="Note: I will answer from the cards.\n\n단심앱입니다 [dansim].",
        ):
            result = ask("뭐 만들었어?", ai_env=_ai_env())

        assert result.answer == "단심앱입니다 [dansim]."

    def test_where_filter_restricts_kinds(self) -> None:
        captured: dict[str, object] = {}

        def _fake_build(**kwargs: object) -> CardIndex:
            captured.update(kwargs)
            return _index()

        with patch.object(ask_mod, "build_card_index", side_effect=_fake_build):
            ask("q", ai_env=_ai_env(), where={"source_kind": "card_project"})
        assert captured["kinds"] == ("project",)

    def test_top_k_passed_to_select(self) -> None:
        index = _index(_entry("x", "project", "X"))
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=[]
        ) as mock_select:
            ask("q", top_k=10, ai_env=_ai_env())
        assert mock_select.call_args.kwargs["max_pages"] == 10

    def test_claude_receives_context(self) -> None:
        index = _index(_entry("x", "project", "X"))
        with patch.object(
            ask_mod, "build_card_index", return_value=index
        ), patch.object(
            ask_mod, "select_related", return_value=["x"]
        ), patch.object(
            ask_mod, "_load_card_text", return_value="# X 내용 풍부"
        ), patch.object(
            ask_mod.ai_api, "complete", return_value="답변"
        ) as mock_complete:
            ask("문의", ai_env=_ai_env())

        prompt = mock_complete.call_args.args[0]
        assert "문의" in prompt
        assert "[x]" in prompt
        assert "X 내용 풍부" in prompt
