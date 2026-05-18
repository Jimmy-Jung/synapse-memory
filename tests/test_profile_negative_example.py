"""extract_profile_facts / extract_decision_patterns 의 negative example 주입 테스트.

핵심 시나리오
- excluded_statements 가 user_prompt 에 bullet 으로 포함됨
- system 프롬프트는 그대로 (prompt cache 보존)
- 빈/None excluded → 섹션 자체가 사라짐
- 100개 cap (_EXCLUDED_MAX_ITEMS)
- 중복/공백 정규화로 batch 내 중복 제거
- DecisionPattern 도 동일 적용

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from synapse_memory.profile import extract as ex_mod
from synapse_memory.profile.extract import (
    _EXCLUDED_MAX_ITEMS,
    _build_excluded_section,
    extract_decision_patterns,
    extract_profile_facts,
)

# ---------------------------------------------------------------------------
# _build_excluded_section
# ---------------------------------------------------------------------------


class TestBuildExcludedSection:
    def test_empty_returns_empty_string(self) -> None:
        assert _build_excluded_section("x", []) == ""

    def test_renders_bullets(self) -> None:
        section = _build_excluded_section(
            "프로필 사실", ["한국어 응답", "iOS 개발"]
        )
        assert "# 제외" in section
        assert "- 한국어 응답" in section
        assert "- iOS 개발" in section

    def test_dedups_within_input(self) -> None:
        section = _build_excluded_section("x", ["A", "a", "  A  ", "B"])
        # 'A' / 'a' / '  A  ' 는 동일 정규화 → 1개만, 첫 등장 형태 유지
        assert section.count("- A") == 1
        assert "- B" in section

    def test_caps_at_max_items(self) -> None:
        many = [f"항목{i}" for i in range(_EXCLUDED_MAX_ITEMS + 20)]
        section = _build_excluded_section("프로필 사실", many)
        assert section.count("\n- ") == _EXCLUDED_MAX_ITEMS
        assert f"원본 {len(many)}개 중 상위" in section


# ---------------------------------------------------------------------------
# extract_profile_facts 통합
# ---------------------------------------------------------------------------


def _write_history(path: Path, *displays: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for d in displays:
            f.write(json.dumps({"display": d}) + "\n")


class TestExtractProfileFactsNegativeExample:
    def test_excluded_appears_in_user_prompt(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan refactor", "/code python")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            captured["system"] = kw.get("system", "")
            return {"facts": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_profile_facts(
                history_path=history,
                sample_lines=10,
                excluded_statements=[
                    "기본 응답 언어는 한국어입니다.",
                    "iOS 개발 주력입니다.",
                ],
            )

        assert "# 제외" in captured["user_prompt"]
        assert "기본 응답 언어는 한국어입니다." in captured["user_prompt"]
        assert "iOS 개발 주력입니다." in captured["user_prompt"]
        # system 프롬프트는 변형되지 않음 → prompt cache 보존
        assert "# 제외" not in captured["system"]

    def test_no_section_when_excluded_empty(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            return {"facts": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_profile_facts(history_path=history, sample_lines=10)

        assert "# 제외" not in captured["user_prompt"]

    def test_none_excluded_same_as_empty(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            return {"facts": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_profile_facts(
                history_path=history,
                sample_lines=10,
                excluded_statements=None,
            )
        assert "# 제외" not in captured["user_prompt"]


# ---------------------------------------------------------------------------
# extract_decision_patterns 통합
# ---------------------------------------------------------------------------


class TestExtractDecisionPatternsNegativeExample:
    def test_excluded_triggers_in_user_prompt(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan", "/code")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            return {"patterns": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_decision_patterns(
                history_path=history,
                sample_lines=10,
                excluded_triggers=[
                    "안전한 자동화 선호",
                    "장기 유지보수성 중시",
                ],
            )

        assert "# 제외" in captured["user_prompt"]
        assert "안전한 자동화 선호" in captured["user_prompt"]
        assert "장기 유지보수성 중시" in captured["user_prompt"]


# ---------------------------------------------------------------------------
# 강한 negative example — misclassified / irrelevant 차단
# ---------------------------------------------------------------------------


class TestStrongExcludedSection:
    def test_strong_section_rendered_with_emphasis(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            return {"facts": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_profile_facts(
                history_path=history,
                sample_lines=10,
                excluded_statements_strong=["오추출된 가짜 사실"],
                excluded_statements=["일반 vault 사실"],
            )

        prompt = captured["user_prompt"]
        # 두 섹션 모두 존재
        assert "# 제외 (강한 차단)" in prompt
        assert "# 제외 — 이미 알고 있거나" in prompt
        # 강한 어조 마커
        assert "명백한 실패" in prompt
        # 각 섹션 위치 — 강한 섹션이 일반 섹션보다 앞
        assert prompt.index("강한 차단") < prompt.index("이미 알고 있거나")
        # 항목 분리 확인
        strong_idx = prompt.index("강한 차단")
        normal_idx = prompt.index("이미 알고 있거나")
        strong_block = prompt[strong_idx:normal_idx]
        normal_block = prompt[normal_idx:]
        assert "오추출된 가짜 사실" in strong_block
        assert "일반 vault 사실" in normal_block
        assert "일반 vault 사실" not in strong_block

    def test_no_strong_section_when_empty(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            return {"facts": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_profile_facts(
                history_path=history,
                sample_lines=10,
                excluded_statements=["A"],
                # excluded_statements_strong 미지정 (None)
            )

        prompt = captured["user_prompt"]
        assert "# 제외 (강한 차단)" not in prompt
        assert "# 제외 — 이미 알고 있거나" in prompt

    def test_strong_patterns_in_decision_extract(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        _write_history(history, "/plan")

        captured: dict[str, Any] = {}

        def fake_complete(prompt: str, **kw: Any) -> dict[str, Any]:
            captured["user_prompt"] = prompt
            return {"patterns": []}

        with patch.object(
            ex_mod.ai_api, "complete_structured", side_effect=fake_complete
        ):
            extract_decision_patterns(
                history_path=history,
                sample_lines=10,
                excluded_triggers_strong=["오추출된 trigger"],
            )

        prompt = captured["user_prompt"]
        assert "# 제외 (강한 차단)" in prompt
        assert "오추출된 trigger" in prompt
