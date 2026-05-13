"""Daily 파이프라인 테스트 — 각 step mock으로.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.daily import (
    STEPS,
    DailyStage,
    StageStatus,
    StepResult,
    render_daily_report,
    run_daily,
    validate_daily_stages,
)


def _ok(summary: str):
    def step() -> str:
        return summary

    return step


def _fail(message: str):
    def step() -> str:
        raise RuntimeError(message)

    return step


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
        # STEPS는 daily 단계 모두 포함
        assert "collect_claude_code" in STEPS
        assert "collect_obsidian" in STEPS
        assert "classify" in STEPS
        assert "generate" in STEPS
        assert "index" in STEPS
        assert "update_profile" in STEPS
        assert "report" in STEPS

    def test_daily_stage_validation_rejects_duplicate_names(self) -> None:
        stages = (
            DailyStage("a", "A", ()),
            DailyStage("a", "B", ()),
        )

        with pytest.raises(ValueError, match="duplicate"):
            validate_daily_stages(stages)

    def test_daily_stage_validation_rejects_unknown_dependency(self) -> None:
        stages = (DailyStage("a", "A", ("missing",)),)

        with pytest.raises(ValueError, match="unknown dependency"):
            validate_daily_stages(stages)

    def test_step_result_status_properties(self) -> None:
        assert StepResult.skipped("generate", "requires classify").status == "skipped"
        assert StepResult.skipped("generate", "requires classify").skip_reason
        assert StepResult.failed("classify", 1.2, "boom").status == "failed"
        assert StepResult.success("index", 0.5, "cards=1").ok is True

    def test_dependency_failure_skips_downstream(self) -> None:
        calls: list[str] = []

        def track(name: str, fn):
            def step():
                calls.append(name)
                return fn()

            return step

        result = run_daily(
            stage_actions={
                "collect_claude_code": track("collect_claude_code", _ok("mirrored=0")),
                "collect_obsidian": track("collect_obsidian", _ok("mirrored=0")),
                "classify": track("classify", _fail("AI provider 미설치")),
                "report": track("report", _ok("report skipped in test")),
            },
            on_log=lambda _line: None,
        )

        by_name = {step.name: step for step in result.steps}
        assert calls == ["collect_claude_code", "collect_obsidian", "classify", "report"]
        assert by_name["classify"].status == StageStatus.FAILED
        assert by_name["generate"].status == StageStatus.SKIPPED
        assert by_name["generate"].skip_reason == "requires classify"
        assert by_name["index"].status == StageStatus.SKIPPED
        assert by_name["update_profile"].status == StageStatus.SKIPPED
        assert result.errors == 1
        assert result.skipped == 3

    def test_resume_from_marks_previous_stages_skipped(self) -> None:
        calls: list[str] = []

        def track(name: str):
            def step() -> str:
                calls.append(name)
                return f"{name}=ok"

            return step

        result = run_daily(
            resume_from="classify",
            stage_actions={
                "classify": track("classify"),
                "generate": track("generate"),
                "index": track("index"),
                "update_profile": track("update_profile"),
                "report": track("report"),
            },
            on_log=lambda _line: None,
        )

        by_name = {step.name: step for step in result.steps}
        assert calls == ["classify", "generate", "index", "update_profile", "report"]
        assert by_name["collect_claude_code"].status == StageStatus.SKIPPED
        assert by_name["collect_claude_code"].skip_reason == "resume before classify"
        assert by_name["collect_obsidian"].status == StageStatus.SKIPPED
        assert by_name["classify"].status == StageStatus.SUCCESS

    def test_unknown_resume_stage_raises_before_execution(self) -> None:
        called = False

        def step() -> str:
            nonlocal called
            called = True
            return "ok"

        with pytest.raises(ValueError, match="unknown daily stage"):
            run_daily(
                resume_from="nope",
                stage_actions={"collect_claude_code": step},
                on_log=lambda _line: None,
            )

        assert called is False

    def test_dry_run_with_resume_from(self, capsys: pytest.CaptureFixture[str]) -> None:
        run_daily(resume_from="classify", dry_run=True)
        out = capsys.readouterr().out

        assert "[ ] collect_claude_code (resume skip)" in out
        assert "[ ] collect_obsidian (resume skip)" in out
        assert "[x] classify" in out

    def test_render_daily_report_excludes_raw_fields(self, tmp_path: Path) -> None:
        result = run_daily(
            stage_actions={
                "collect_claude_code": _ok("mirrored=0"),
                "collect_obsidian": _ok("mirrored=0"),
                "classify": _fail("AI provider 미설치"),
                "report": _ok("report skipped in test"),
            },
            on_log=lambda _line: None,
        )

        text = render_daily_report(result, date="2026-05-12", est_usd=0.0)

        assert "prompt" not in text.lower()
        assert "response" not in text.lower()
        assert "classify" in text
        assert "requires classify" in text
