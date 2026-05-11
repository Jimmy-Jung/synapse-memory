"""Daily 파이프라인 테스트 — 각 step mock으로.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import pytest

from synapse_memory.daily import STEPS, run_daily


class TestRunDaily:
    def test_dry_run_lists_steps(self, capsys: pytest.CaptureFixture) -> None:
        result = run_daily(dry_run=True)
        captured = capsys.readouterr()
        for s in STEPS:
            assert s in captured.out
        assert result.steps == []

    def test_dry_run_with_only(self, capsys: pytest.CaptureFixture) -> None:
        run_daily(only={"collect_obsidian", "index"}, dry_run=True)
        out = capsys.readouterr().out
        assert "[x] collect_obsidian" in out
        assert "[x] index" in out
        assert "[ ] collect_claude_code" in out

    def test_skip_works(self, capsys: pytest.CaptureFixture) -> None:
        run_daily(skip={"update_profile", "generate"}, dry_run=True)
        out = capsys.readouterr().out
        assert "[ ] update_profile" in out
        assert "[ ] generate" in out
        assert "[x] collect_claude_code" in out

    def test_steps_constant_complete(self) -> None:
        # STEPS는 6개 단계 모두 포함
        assert "collect_claude_code" in STEPS
        assert "collect_obsidian" in STEPS
        assert "classify" in STEPS
        assert "generate" in STEPS
        assert "index" in STEPS
        assert "update_profile" in STEPS
