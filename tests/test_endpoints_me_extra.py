"""me what-did-i-think / decide 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import synapse_memory.endpoints.me as me_mod
from synapse_memory.endpoints.me import (
    WhatDidIThinkResult,
    _load_profile_text,
    decide,
    what_did_i_think,
)
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.rag.hybrid import RetrievalHit
from synapse_memory.rag.vector_store import VectorRecord
from synapse_memory.storage.l0 import L0_ENV_VAR
from synapse_memory.storage.last_response import load_last_answer


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(claude_path="/x/claude", claude_version="2.1", model="sonnet")


def _rec(cid: str, doc: str, kind: str = "card_project") -> VectorRecord:
    return VectorRecord(
        id=f"{kind}:{cid}",
        document=doc,
        embedding=[0.0],
        metadata={"source_kind": kind, "card_id": cid, "display_name": cid},
    )


class TestWhatDidIThink:
    def test_returns_answer_with_sources(self) -> None:
        store = MagicMock()
        store.query.return_value = [
            (_rec("dansim", "# 단심\n## 회고\nTCA 도입"), 0.3),
            (_rec("이력서-2026", "# 클린 아키텍처 도입"), 0.4),
        ]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="TCA를 도입했습니다 [dansim].",
        ):
            result = what_did_i_think(
                "TCA 아키텍처", store=store, ai_env=_ai_env()
            )

        assert isinstance(result, WhatDidIThinkResult)
        assert "TCA" in result.answer
        assert result.source_ids == ["dansim", "이력서-2026"]

    def test_records_last_answer_reference(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        store = MagicMock()
        store.query.return_value = [(_rec("dansim", "# 단심"), 0.3)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="답변 [dansim].",
        ):
            what_did_i_think("TCA", store=store, ai_env=_ai_env())

        ref = load_last_answer()
        assert ref is not None
        assert ref.command == "me.generate.recall"  # R-6: unified me.generate.<recipe>
        assert ref.citations[0].target_ref == "dansim"

    def test_strips_claude_meta_prefix(self) -> None:
        store = MagicMock()
        store.query.return_value = [(_rec("x", "# X"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="Insight: 이 답변은 개인 자료를 바탕으로 합니다.\n\n실제 답변 [x]",
        ):
            result = what_did_i_think("x", store=store, ai_env=_ai_env())
        assert result.answer == "실제 답변 [x]"

    def test_empty_topic_raises(self) -> None:
        with pytest.raises(ValueError):
            what_did_i_think("", store=MagicMock(), ai_env=_ai_env())

    def test_no_results_returns_help(self) -> None:
        store = MagicMock()
        store.query.return_value = []
        with patch.object(me_mod, "embed_query", return_value=[0.0]):
            result = what_did_i_think("x", store=store, ai_env=_ai_env())
        assert "rag index" in result.answer.lower()

    def test_hybrid_uses_hybrid_search_order(self) -> None:
        store = MagicMock()
        hybrid_record = _rec("danggeun", "# 당근마켓")
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch.object(
            me_mod,
            "hybrid_search",
            return_value=[
                RetrievalHit(
                    record=hybrid_record,
                    dense_rank=2,
                    dense_distance=0.4,
                    bm25_rank=1,
                    bm25_score=3.0,
                    rrf_score=0.03,
                )
            ],
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="당근마켓을 검토했습니다 [danggeun].",
        ):
            result = what_did_i_think(
                "당근마켓",
                store=store,
                ai_env=_ai_env(),
                hybrid=True,
            )

        assert result.source_ids == ["danggeun"]

    def test_hybrid_timeline_combination_rejected(self) -> None:
        with pytest.raises(ValueError):
            what_did_i_think(
                "당근마켓",
                store=MagicMock(),
                ai_env=_ai_env(),
                hybrid=True,
                by="time",
            )

    def test_hybrid_prompt_uses_redacted_raw_context(self) -> None:
        store = MagicMock()
        raw_record = VectorRecord(
            id="raw_obsidian:abc:0",
            document="연락처 [EMAIL_1] 당근마켓",
            embedding=[0.0],
            metadata={
                "source_kind": "raw_obsidian",
                "path": "10_Active/secret.md",
                "chunk_index": 0,
                "display_name": "secret.md",
            },
        )
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch.object(
            me_mod,
            "hybrid_search",
            return_value=[
                RetrievalHit(
                    record=raw_record,
                    dense_rank=None,
                    dense_distance=None,
                    bm25_rank=1,
                    bm25_score=3.0,
                    rrf_score=0.02,
                )
            ],
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="당근마켓을 검토했습니다 [raw_obsidian:abc:0].",
        ) as mock_complete:
            what_did_i_think(
                "당근마켓",
                store=store,
                ai_env=_ai_env(),
                hybrid=True,
            )

        prompt = mock_complete.call_args.args[0]
        assert "user@example.com" not in prompt
        assert "[EMAIL_1]" in prompt


class TestDecide:
    def test_without_profile(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.query.return_value = [(_rec("x", "# X 정보"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", return_value="추천: A"
        ):
            result = decide(
                "어떤 회사 지원?",
                store=store,
                ai_env=_ai_env(),
                vault_path=tmp_path,
            )
        assert result.profile_used is False
        assert "추천" in result.answer
        assert result.source_ids == ["x"]

    def test_decide_records_last_answer_reference(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        store = MagicMock()
        store.query.return_value = [(_rec("x", "# X 정보"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="추천: A",
        ):
            decide(
                "어떤 회사 지원?",
                store=store,
                ai_env=_ai_env(),
                vault_path=tmp_path,
            )

        ref = load_last_answer()
        assert ref is not None
        assert ref.command == "me.generate.decide"  # R-6: unified me.generate.<recipe>
        assert ref.citations[0].target_ref == "x"

    def test_strips_claude_meta_prefix(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.query.return_value = [(_rec("x", "# X 정보"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="Analysis: 사용자의 Profile을 검토했습니다.\n\n**추천**: A",
        ):
            result = decide(
                "어떤 회사 지원?",
                store=store,
                ai_env=_ai_env(),
                vault_path=tmp_path,
            )
        assert result.answer == "**추천**: A"

    def test_with_profile(self, tmp_path: Path) -> None:
        # Profile.md 생성
        ai_dir = tmp_path / "90_System" / "AI"
        ai_dir.mkdir(parents=True)
        (ai_dir / "Profile.md").write_text(
            "# Profile\n- 한국어 응답 선호\n- 단계별 작업", encoding="utf-8"
        )
        store = MagicMock()
        store.query.return_value = [(_rec("x", "# X"), 0.4)]

        captured_prompt: list[str] = []

        def fake_complete(prompt, **kwargs):
            captured_prompt.append(prompt)
            return "추천"

        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake_complete
        ):
            result = decide(
                "결정",
                store=store,
                ai_env=_ai_env(),
                vault_path=tmp_path,
            )
        assert result.profile_used is True
        assert "한국어 응답 선호" in captured_prompt[0]

    def test_empty_situation_raises(self) -> None:
        with pytest.raises(ValueError):
            decide("", store=MagicMock(), ai_env=_ai_env())


class TestLoadProfileText:
    def test_missing_returns_empty(self, tmp_path: Path) -> None:
        assert _load_profile_text(tmp_path) == ""

    def test_loads_multiple_files(self, tmp_path: Path) -> None:
        ai_dir = tmp_path / "90_System" / "AI"
        ai_dir.mkdir(parents=True)
        (ai_dir / "Profile.md").write_text("# Profile\nA", encoding="utf-8")
        (ai_dir / "DecisionPatterns.md").write_text("# Patterns\nB", encoding="utf-8")
        text = _load_profile_text(tmp_path)
        assert "Profile" in text
        assert "Patterns" in text
        assert "A" in text and "B" in text
