"""Profile 추출 테스트.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import synapse_memory.profile.extract as ex_mod
from synapse_memory.profile.extract import (
    MEMORY_INBOX_SUBPATH,
    _read_history_tail,
    extract_decision_patterns,
    extract_profile_facts,
    save_profile_update,
)
from synapse_memory.profile.schema import (
    PROFILE_CATEGORIES,
    DecisionPattern,
    ProfileFact,
)
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.llm.claude import ClaudeEnvironment, ClaudeError


def _claude_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude", claude_version="2.1", model="sonnet"
    )


def _apfel_disabled() -> ApfelEnvironment:
    return ApfelEnvironment(None, None, "0", False)


# ---------------------------------------------------------------------------
# _read_history_tail
# ---------------------------------------------------------------------------


class TestReadHistoryTail:
    def test_extracts_display_field(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        path.write_text(
            json.dumps({"display": "/init", "project": "/x"}) + "\n"
            + json.dumps({"display": "/plan refactor", "project": "/x"}) + "\n",
            encoding="utf-8",
        )
        text = _read_history_tail(path, 100)
        assert "/init" in text
        assert "/plan refactor" in text

    def test_tail_only(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        lines = [json.dumps({"display": f"cmd-{i}"}) for i in range(50)]
        path.write_text("\n".join(lines), encoding="utf-8")
        text = _read_history_tail(path, 5)
        # 마지막 5개만
        assert "cmd-45" in text
        assert "cmd-49" in text
        assert "cmd-0" not in text

    def test_missing_file_empty(self, tmp_path: Path) -> None:
        assert _read_history_tail(tmp_path / "nope", 10) == ""

    def test_handles_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "h.jsonl"
        path.write_text("invalid\n{\"display\":\"ok\"}\n", encoding="utf-8")
        text = _read_history_tail(path, 10)
        assert "ok" in text
        assert "invalid" not in text


# ---------------------------------------------------------------------------
# extract_profile_facts
# ---------------------------------------------------------------------------


class TestExtractProfileFacts:
    def test_parses_response(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        history.write_text(
            json.dumps({"display": "/plan refactor"}) + "\n", encoding="utf-8"
        )

        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value={
                "facts": [
                    {
                        "category": "work_style",
                        "statement": "단계별 의사코드 후 코드",
                        "confidence": 0.9,
                    },
                    {
                        "category": "preference",
                        "statement": "한국어 응답",
                        "confidence": 0.95,
                    },
                ]
            },
        ):
            facts = extract_profile_facts(
                history_path=history,
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )
        assert len(facts) == 2
        assert facts[0].category == "work_style"
        assert facts[1].statement == "한국어 응답"
        assert facts[1].confidence == 0.95

    def test_filters_invalid_category(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value={
                "facts": [
                    {"category": "weirdkind", "statement": "x", "confidence": 0.9},
                    {"category": "tech", "statement": "Swift", "confidence": 0.9},
                ]
            },
        ):
            facts = extract_profile_facts(
                history_path=history,
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )
        assert len(facts) == 1
        assert facts[0].category == "tech"

    def test_clamps_confidence(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value={
                "facts": [
                    {"category": "tech", "statement": "x", "confidence": 2.5},
                ]
            },
        ):
            facts = extract_profile_facts(
                history_path=history,
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )
        assert facts[0].confidence == 1.0

    def test_missing_history_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            extract_profile_facts(
                history_path=tmp_path / "missing.jsonl",
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )

    def test_empty_facts_returned(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value={"facts": []},
        ):
            facts = extract_profile_facts(
                history_path=history,
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )
        assert facts == []

    def test_non_dict_response_raises(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value="not a dict",
        ):
            with pytest.raises(ClaudeError):
                extract_profile_facts(
                    history_path=history,
                    claude_env=_claude_env(),
                    apfel_env=_apfel_disabled(),
                )


# ---------------------------------------------------------------------------
# extract_decision_patterns
# ---------------------------------------------------------------------------


class TestExtractDecisionPatterns:
    def test_parses_response(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value={
                "patterns": [
                    {
                        "trigger": "큰 작업 시작",
                        "action": "단계별 의사코드 제시",
                        "rationale": "확인 후 진행",
                        "confidence": 0.8,
                    }
                ]
            },
        ):
            patterns = extract_decision_patterns(
                history_path=history,
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )
        assert len(patterns) == 1
        assert patterns[0].trigger == "큰 작업 시작"
        assert patterns[0].confidence == 0.8

    def test_skip_incomplete(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.claude_api,
            "complete_structured",
            return_value={
                "patterns": [
                    {"trigger": "", "action": "x"},  # trigger 빈 문자열
                    {"trigger": "y", "action": "", "rationale": ""},  # action 빈
                    {
                        "trigger": "valid",
                        "action": "valid action",
                        "rationale": "ok",
                        "confidence": 0.7,
                    },
                ]
            },
        ):
            patterns = extract_decision_patterns(
                history_path=history,
                claude_env=_claude_env(),
                apfel_env=_apfel_disabled(),
            )
        assert len(patterns) == 1
        assert patterns[0].trigger == "valid"


# ---------------------------------------------------------------------------
# save_profile_update
# ---------------------------------------------------------------------------


class TestSaveProfileUpdate:
    def test_creates_in_memory_inbox(self, tmp_path: Path) -> None:
        facts = [
            ProfileFact(
                category="work_style",
                statement="단계별 의사코드",
                confidence=0.9,
                extracted_at="2026-05-10",
            )
        ]
        patterns = [
            DecisionPattern(
                trigger="큰 작업",
                action="의사코드 먼저",
                rationale="확인 후 진행",
                confidence=0.8,
                extracted_at="2026-05-10",
            )
        ]
        path = save_profile_update(facts, patterns, vault_path=tmp_path)

        assert path.is_file()
        assert path.parent.relative_to(tmp_path) == MEMORY_INBOX_SUBPATH
        content = path.read_text(encoding="utf-8")
        assert "type: profile_update" in content
        assert "단계별 의사코드" in content
        assert "큰 작업" in content
        assert "work_style" in content

    def test_only_facts(self, tmp_path: Path) -> None:
        facts = [
            ProfileFact(
                category="tech",
                statement="Swift",
                confidence=0.9,
                extracted_at="2026-05-10",
            )
        ]
        path = save_profile_update(facts, None, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Swift" in content
        assert "ProfileFact 후보" in content
        # DecisionPattern 섹션 헤더 (## DecisionPattern 후보)는 안 들어가야
        assert "## DecisionPattern 후보" not in content

    def test_empty_inputs(self, tmp_path: Path) -> None:
        path = save_profile_update([], [], vault_path=tmp_path)
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert "fact_count: 0" in content


def test_profile_categories_sanity() -> None:
    assert "work_style" in PROFILE_CATEGORIES
    assert "preference" in PROFILE_CATEGORIES
    assert "value" in PROFILE_CATEGORIES
