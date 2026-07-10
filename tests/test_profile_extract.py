"""Profile 추출 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import synapse_memory.profile.extract as ex_mod
from synapse_memory.llm.ai_api import AIError
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.profile.extract import (
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


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude", claude_version="2.1", model="sonnet"
    )




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
    def test_default_model_uses_update_profile_task_route(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        history = tmp_path / "history.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        captured: dict[str, str | None] = {}

        monkeypatch.setattr(
            ex_mod.ai_api,
            "resolve_model_for_task",
            lambda task, **_kwargs: "gpt-5.6-terra" if task == "update_profile" else None,
        )

        def fake_complete(*_args, model=None, **_kwargs):
            captured["model"] = model
            return {"facts": []}

        monkeypatch.setattr(ex_mod.ai_api, "complete_structured", fake_complete)
        extract_profile_facts(
            history_path=history,
            ai_env=SimpleNamespace(provider="codex", model="gpt-5.6-sol"),
        )

        assert captured["model"] == "gpt-5.6-terra"

    def test_parses_response(self, tmp_path: Path) -> None:
        history = tmp_path / "history.jsonl"
        history.write_text(
            json.dumps({"display": "/plan refactor"}) + "\n", encoding="utf-8"
        )

        with patch.object(
            ex_mod.ai_api,
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
                ai_env=_ai_env(),
            )
        assert len(facts) == 2
        assert facts[0].category == "work_style"
        assert facts[1].statement == "한국어 응답"
        assert facts[1].confidence == 0.95

    def test_filters_invalid_category(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.ai_api,
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
                ai_env=_ai_env(),
            )
        assert len(facts) == 1
        assert facts[0].category == "tech"

    def test_clamps_confidence(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.ai_api,
            "complete_structured",
            return_value={
                "facts": [
                    {"category": "tech", "statement": "x", "confidence": 2.5},
                ]
            },
        ):
            facts = extract_profile_facts(
                history_path=history,
                ai_env=_ai_env(),
            )
        assert facts[0].confidence == 1.0

    def test_missing_history_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            extract_profile_facts(
                history_path=tmp_path / "missing.jsonl",
                codex_history_path=tmp_path / "missing_codex.jsonl",
                codex_sessions_path=tmp_path / "missing_codex_sessions",
                ai_env=_ai_env(),
            )

    def test_empty_facts_returned(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.ai_api,
            "complete_structured",
            return_value={"facts": []},
        ):
            facts = extract_profile_facts(
                history_path=history,
                ai_env=_ai_env(),
            )
        assert facts == []

    def test_non_dict_response_raises(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.ai_api,
            "complete_structured",
            return_value="not a dict",
        ), pytest.raises(AIError):
            extract_profile_facts(
                history_path=history,
                ai_env=_ai_env(),
            )


# ---------------------------------------------------------------------------
# extract_decision_patterns
# ---------------------------------------------------------------------------


class TestExtractDecisionPatterns:
    def test_default_model_uses_update_profile_task_route(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        history = tmp_path / "history.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        captured: dict[str, str | None] = {}

        monkeypatch.setattr(
            ex_mod.ai_api,
            "resolve_model_for_task",
            lambda task, **_kwargs: "gpt-5.6-terra" if task == "update_profile" else None,
        )

        def fake_complete(*_args, model=None, **_kwargs):
            captured["model"] = model
            return {"patterns": []}

        monkeypatch.setattr(ex_mod.ai_api, "complete_structured", fake_complete)
        extract_decision_patterns(
            history_path=history,
            ai_env=SimpleNamespace(provider="codex", model="gpt-5.6-sol"),
        )

        assert captured["model"] == "gpt-5.6-terra"

    def test_parses_response(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.ai_api,
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
                ai_env=_ai_env(),
            )
        assert len(patterns) == 1
        assert patterns[0].trigger == "큰 작업 시작"
        assert patterns[0].confidence == 0.8

    def test_skip_incomplete(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(json.dumps({"display": "x"}) + "\n", encoding="utf-8")
        with patch.object(
            ex_mod.ai_api,
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
                ai_env=_ai_env(),
            )
        assert len(patterns) == 1
        assert patterns[0].trigger == "valid"


# ---------------------------------------------------------------------------
# save_profile_update
# ---------------------------------------------------------------------------


class TestSaveProfileUpdate:
    def test_creates_profile_wiki_page_without_flat_files(
        self,
        tmp_path: Path,
    ) -> None:
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
        assert path == tmp_path / "Profile" / "user-profile.md"
        assert not (tmp_path / "90_System" / "AI" / "Profile.md").exists()
        assert not (tmp_path / "90_System" / "AI" / "DecisionPatterns.md").exists()
        content = path.read_text(encoding="utf-8")
        assert "type: profile" in content
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
        assert "Profile Facts" in content
        assert "## Decision Patterns" not in content

    def test_empty_inputs(self, tmp_path: Path) -> None:
        path = save_profile_update([], [], vault_path=tmp_path)
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert "fact_count: 0" in content


class TestSaveProfileUpdateLedgerMeta:
    """B 묶음 — ledger 메타가 candidate 파일에 함께 출력되어 정렬·판단 보조."""

    def test_frontmatter_includes_avg_confidence(self, tmp_path: Path) -> None:
        facts = [
            ProfileFact(category="tech", statement="A", confidence=0.9,
                        extracted_at="2026-05-18"),
            ProfileFact(category="tech", statement="B", confidence=0.5,
                        extracted_at="2026-05-18"),
        ]
        path = save_profile_update(facts, [], vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "fact_avg_confidence: '0.70'" in content
        assert "pattern_avg_confidence: '0.00'" in content

    def test_appends_to_existing_profile_page(self, tmp_path: Path) -> None:
        first = ProfileFact(
            category="tech",
            statement="Swift",
            confidence=0.9,
            extracted_at="2026-05-18",
        )
        second = ProfileFact(
            category="preference",
            statement="한국어 응답",
            confidence=0.8,
            extracted_at="2026-05-19",
        )
        save_profile_update(
            [first],
            [],
            vault_path=tmp_path,
            date=datetime.date(2026, 5, 18),
        )
        path = save_profile_update(
            [second],
            [],
            vault_path=tmp_path,
            date=datetime.date(2026, 5, 19),
        )
        content = path.read_text(encoding="utf-8")
        assert "Swift" in content
        assert "한국어 응답" in content

    def test_meta_suffix_when_ledger_passed(self, tmp_path: Path) -> None:
        from synapse_memory.profile.ledger import (
            LedgerEntry,
            record_extraction,
        )

        facts = [
            ProfileFact(category="preference", statement="한국어 응답 선호",
                        confidence=0.85, extracted_at="2026-05-18"),
        ]
        ledger: dict[str, LedgerEntry] = {}
        # 4일 누적 시뮬레이션
        import datetime as _dt
        for day in (15, 16, 17, 18):
            record_extraction(
                ledger, facts, [],
                today=_dt.date(2026, 5, day),
            )

        path = save_profile_update(facts, [], vault_path=tmp_path, ledger=ledger)
        content = path.read_text(encoding="utf-8")
        assert "↳ ledger: 4회 등장" in content
        assert "peak 0.85" in content
        assert "첫 2026-05-15" in content

    def test_meta_omitted_when_no_ledger(self, tmp_path: Path) -> None:
        facts = [
            ProfileFact(category="tech", statement="A", confidence=0.9,
                        extracted_at="2026-05-18"),
        ]
        content = save_profile_update(facts, [], vault_path=tmp_path).read_text(
            encoding="utf-8"
        )
        # 안내문에는 `↳ ledger:` 표현이 포함되지만 bullet 형태 (`  ↳ ledger: N회`) 는 없어야.
        for line in content.splitlines():
            if line.startswith("  ↳ ledger:"):
                raise AssertionError(f"unexpected bullet meta line: {line!r}")

    def test_sort_by_ledger_peak_then_count(self, tmp_path: Path) -> None:
        import datetime as _dt

        from synapse_memory.profile.ledger import (
            LedgerEntry,
            record_extraction,
        )

        f_strong = ProfileFact(category="tech", statement="강한 신호",
                               confidence=0.7, extracted_at="2026-05-18")
        f_weak = ProfileFact(category="tech", statement="약한 신호",
                             confidence=0.7, extracted_at="2026-05-18")
        ledger: dict[str, LedgerEntry] = {}
        # 강한 신호: 5번 등장, peak 0.95
        for day, conf in [(14, 0.7), (15, 0.8), (16, 0.85), (17, 0.9), (18, 0.95)]:
            record_extraction(
                ledger,
                [ProfileFact(category="tech", statement="강한 신호",
                             confidence=conf, extracted_at="2026-05-18")],
                [],
                today=_dt.date(2026, 5, day),
            )
        # 약한 신호: 2번 등장, peak 0.7
        for day in (17, 18):
            record_extraction(
                ledger,
                [ProfileFact(category="tech", statement="약한 신호",
                             confidence=0.7, extracted_at="2026-05-18")],
                [],
                today=_dt.date(2026, 5, day),
            )

        path = save_profile_update(
            [f_weak, f_strong], [], vault_path=tmp_path, ledger=ledger
        )
        content = path.read_text(encoding="utf-8")
        idx_strong = content.index("강한 신호")
        idx_weak = content.index("약한 신호")
        assert idx_strong < idx_weak  # 강한 신호가 먼저 노출


def test_profile_categories_sanity() -> None:
    assert "work_style" in PROFILE_CATEGORIES
    assert "preference" in PROFILE_CATEGORIES
    assert "value" in PROFILE_CATEGORIES


# ---------------------------------------------------------------------------
# _read_codex_sessions_tail — 0.15.7: history.jsonl stale fallback
# ---------------------------------------------------------------------------


def _write_rollout(path: Path, *user_texts: str) -> None:
    """Codex 0.131 rollout-*.jsonl 형식 — session_meta + user response_item."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        json.dumps(
            {
                "timestamp": "2026-05-19T11:00:00.000Z",
                "type": "session_meta",
                "payload": {"cwd": "/work/sample", "cli_version": "0.131.0"},
            }
        )
    ]
    for t in user_texts:
        lines.append(
            json.dumps(
                {
                    "timestamp": "2026-05-19T11:00:01.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": t}],
                    },
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestReadCodexSessionsTail:
    def test_extracts_user_messages_from_rollout(self, tmp_path: Path) -> None:
        rollout = tmp_path / "2026" / "05" / "19" / "rollout-a.jsonl"
        _write_rollout(rollout, "토스뱅크 지원 자기소개서 작성", "FPS DRM 흐름 정리")
        from synapse_memory.profile.extract import _read_codex_sessions_tail

        text = _read_codex_sessions_tail(tmp_path, max_messages=10)
        assert "토스뱅크 지원 자기소개서 작성" in text
        assert "FPS DRM 흐름 정리" in text
        assert text.startswith("[codex-session]")

    def test_skips_agents_md_instruction_prefix(self, tmp_path: Path) -> None:
        rollout = tmp_path / "2026" / "05" / "19" / "rollout-a.jsonl"
        _write_rollout(
            rollout,
            "# AGENTS.md instructions for /work/sample\n실제 발화 아님",
            "이건 진짜 발화입니다",
        )
        from synapse_memory.profile.extract import _read_codex_sessions_tail

        text = _read_codex_sessions_tail(tmp_path, max_messages=10)
        assert "AGENTS.md instructions" not in text
        assert "이건 진짜 발화입니다" in text

    def test_max_messages_cap(self, tmp_path: Path) -> None:
        rollout = tmp_path / "2026" / "05" / "19" / "rollout-a.jsonl"
        _write_rollout(rollout, *[f"메시지-{i}" for i in range(20)])
        from synapse_memory.profile.extract import _read_codex_sessions_tail

        text = _read_codex_sessions_tail(tmp_path, max_messages=5)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        assert len(lines) == 5

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        from synapse_memory.profile.extract import _read_codex_sessions_tail

        assert _read_codex_sessions_tail(tmp_path / "nope", max_messages=10) == ""

    def test_zero_max_messages_returns_empty(self, tmp_path: Path) -> None:
        rollout = tmp_path / "2026" / "05" / "19" / "rollout-a.jsonl"
        _write_rollout(rollout, "메시지")
        from synapse_memory.profile.extract import _read_codex_sessions_tail

        assert _read_codex_sessions_tail(tmp_path, max_messages=0) == ""

    def test_ignores_non_user_response_items(self, tmp_path: Path) -> None:
        rollout = tmp_path / "2026" / "05" / "19" / "rollout-a.jsonl"
        rollout.parent.mkdir(parents=True, exist_ok=True)
        rollout.write_text(
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "어시 답변"}],
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "response_item",
                    "payload": {"type": "function_call", "name": "shell"},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "유저 발화"}],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        from synapse_memory.profile.extract import _read_codex_sessions_tail

        text = _read_codex_sessions_tail(tmp_path, max_messages=10)
        assert "유저 발화" in text
        assert "어시 답변" not in text
