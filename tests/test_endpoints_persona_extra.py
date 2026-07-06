"""persona what-did-i-think / decide 테스트 (020 provider-only).

벡터/임베딩/hybrid 의존 제거. 실제 ProjectCard 를 vault 에 심고, pipeline 의
``select_related``/``ai_api_complete`` 를
monkeypatch 한다. decide out-of-domain 가드는 distance 임계 → "provider 0건 선별 = 거부"
로 변경됨.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_memory.cards.project import ProjectCard, save_project_card
from synapse_memory.endpoints.persona import (
    WhatDidIThinkResult,
    _load_profile_text,
    decide,
    what_did_i_think,
)
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.storage.l0 import L0_ENV_VAR
from synapse_memory.storage.last_response import load_last_answer


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(claude_path="/x/claude", claude_version="2.1", model="sonnet")


def _seed(vault: Path, *project_ids: str) -> None:
    for pid in project_ids:
        save_project_card(
            ProjectCard(
                project_id=pid,
                display_name=pid,
                status="active",
                body=f"# {pid} 본문",
            ),
            vault_path=vault,
        )


class TestWhatDidIThink:
    def test_returns_answer_with_sources(self, tmp_path: Path) -> None:
        _seed(tmp_path, "dansim", "이력서-2026")
        with patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=["dansim", "이력서-2026"],
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="TCA를 도입했습니다 [dansim].",
        ):
            result = what_did_i_think(
                "TCA 아키텍처", ai_env=_ai_env(), vault_path=tmp_path
            )

        assert isinstance(result, WhatDidIThinkResult)
        assert "TCA" in result.answer
        assert set(result.source_ids) == {"dansim", "이력서-2026"}

    def test_select_related_called_once(self, tmp_path: Path) -> None:
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ) as mock_select, patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", return_value="답변 [x]."
        ):
            what_did_i_think("TCA", ai_env=_ai_env(), vault_path=tmp_path)
        assert mock_select.call_count == 1

    def test_records_last_answer_reference(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        _seed(tmp_path, "dansim")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["dansim"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="답변 [dansim].",
        ):
            what_did_i_think("TCA", ai_env=_ai_env(), vault_path=tmp_path)

        ref = load_last_answer()
        assert ref is not None
        assert ref.command == "persona.generate.recall"
        assert ref.citations[0].target_ref == "dansim"

    def test_strips_claude_meta_prefix(self, tmp_path: Path) -> None:
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="Insight: 이 답변은 개인 자료를 바탕으로 합니다.\n\n실제 답변 [x]",
        ):
            result = what_did_i_think("x", ai_env=_ai_env(), vault_path=tmp_path)
        assert result.answer == "실제 답변 [x]"

    def test_empty_topic_raises(self) -> None:
        with pytest.raises(ValueError):
            what_did_i_think("", ai_env=_ai_env())

    def test_no_selection_returns_help(self, tmp_path: Path) -> None:
        _seed(tmp_path, "x")
        with patch("synapse_memory.recipes.pipeline.select_related", return_value=[]):
            result = what_did_i_think("x", ai_env=_ai_env(), vault_path=tmp_path)
        assert "자료 없음" in result.answer

    def test_hybrid_timeline_combination_rejected(self) -> None:
        with pytest.raises(ValueError):
            what_did_i_think(
                "당근마켓",
                ai_env=_ai_env(),
                hybrid=True,
                by="time",
            )


class TestDecide:
    def test_without_profile(self, tmp_path: Path) -> None:
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", return_value="추천: A"
        ):
            result = decide("어떤 회사 지원?", ai_env=_ai_env(), vault_path=tmp_path)
        assert result.profile_used is False
        assert "추천" in result.answer
        assert result.source_ids == ["x"]

    def test_select_related_called_once(self, tmp_path: Path) -> None:
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ) as mock_select, patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", return_value="추천: A"
        ):
            decide("어떤 회사 지원?", ai_env=_ai_env(), vault_path=tmp_path)
        assert mock_select.call_count == 1

    def test_decide_records_last_answer_reference(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", return_value="추천: A"
        ):
            decide("어떤 회사 지원?", ai_env=_ai_env(), vault_path=tmp_path)

        ref = load_last_answer()
        assert ref is not None
        assert ref.command == "persona.generate.decide"
        assert ref.citations[0].target_ref == "x"

    def test_strips_claude_meta_prefix(self, tmp_path: Path) -> None:
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="Analysis: 사용자의 Profile을 검토했습니다.\n\n**추천**: A",
        ):
            result = decide("어떤 회사 지원?", ai_env=_ai_env(), vault_path=tmp_path)
        assert result.answer == "**추천**: A"

    def test_with_profile(self, tmp_path: Path) -> None:
        ai_dir = tmp_path / "90_System" / "AI"
        ai_dir.mkdir(parents=True)
        (ai_dir / "Profile.md").write_text(
            "# Profile\n- 한국어 응답 선호\n- 단계별 작업", encoding="utf-8"
        )
        _seed(tmp_path, "x")

        captured_prompt: list[str] = []

        def fake_complete(prompt, **kwargs):
            captured_prompt.append(prompt)
            return "추천"

        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake_complete
        ):
            result = decide("결정", ai_env=_ai_env(), vault_path=tmp_path)
        assert result.profile_used is True
        assert "한국어 응답 선호" in captured_prompt[0]

    def test_empty_situation_raises(self) -> None:
        with pytest.raises(ValueError):
            decide("")

    # out-of-domain 가드 (020: provider 0건 선별 = 거부) -----------------------

    def test_guard_rejects_when_provider_selects_nothing(self, tmp_path: Path) -> None:
        """provider 0건 선별 → LLM 호출 안 함, 명시적 거부 응답."""
        _seed(tmp_path, "x")
        with patch("synapse_memory.recipes.pipeline.select_related", return_value=[]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete"
        ) as mock_complete:
            result = decide("이직할까?", ai_env=_ai_env(), vault_path=tmp_path)

        mock_complete.assert_not_called()  # critical: LLM 호출 차단
        assert result.profile_used is False
        assert result.source_ids == []
        assert "신뢰 가능한 답변 불가" in result.answer or "자료 불충분" in result.answer

    def test_guard_rejects_when_index_empty(self, tmp_path: Path) -> None:
        """카드가 0개인 vault → 0건 선별과 동일하게 거부."""
        with patch(
            "synapse_memory.recipes.pipeline.ai_api_complete"
        ) as mock_complete:
            result = decide("이직할까?", ai_env=_ai_env(), vault_path=tmp_path)
        mock_complete.assert_not_called()
        assert result.source_ids == []

    def test_guard_passes_when_provider_selects(self, tmp_path: Path) -> None:
        """provider 가 1건 이상 선별 → 통과, LLM 호출됨."""
        _seed(tmp_path, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related", return_value=["x"]
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", return_value="추천: A"
        ) as mock_complete:
            result = decide("결정", ai_env=_ai_env(), vault_path=tmp_path)

        mock_complete.assert_called_once()
        assert "추천" in result.answer


class TestLoadProfileText:
    def test_missing_returns_empty(self, tmp_path: Path) -> None:
        assert _load_profile_text(tmp_path) == ""

    def test_loads_full_profile_no_5000_char_cap(self, tmp_path: Path) -> None:
        """B2: 5000자 silent truncation 제거 회귀 검증."""
        ai_dir = tmp_path / "90_System" / "AI"
        ai_dir.mkdir(parents=True)
        long_profile = "# Profile\n" + ("x" * 5900) + "\nMARKER_END"
        assert len(long_profile) > 5000
        (ai_dir / "Profile.md").write_text(long_profile, encoding="utf-8")

        loaded = _load_profile_text(tmp_path)

        assert len(loaded) > 5000
        assert "MARKER_END" in loaded

    def test_loads_multiple_files(self, tmp_path: Path) -> None:
        ai_dir = tmp_path / "90_System" / "AI"
        ai_dir.mkdir(parents=True)
        (ai_dir / "Profile.md").write_text("# Profile\nA", encoding="utf-8")
        (ai_dir / "DecisionPatterns.md").write_text("# Patterns\nB", encoding="utf-8")
        text = _load_profile_text(tmp_path)
        assert "Profile" in text
        assert "Patterns" in text
        assert "A" in text and "B" in text
