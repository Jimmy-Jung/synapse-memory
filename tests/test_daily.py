"""Daily single ingest pipeline tests.

저자: JunyoungJung
작성일: 2026-07-06
"""

from __future__ import annotations

from pathlib import Path

import pytest

import synapse_memory.daily as daily_mod
from synapse_memory.daily import (
    STEPS,
    DailyStage,
    StageStatus,
    StepResult,
    _build_stage_actions,
    _humanize_stage_summary,
    render_daily_report,
    run_daily,
    validate_daily_stages,
)
from synapse_memory.llm import ai_api


def _ok(summary: str):
    def step() -> str:
        return summary

    return step


def _fail(message: str):
    def step() -> str:
        raise RuntimeError(message)

    return step


@pytest.fixture(autouse=True)
def _daily_status_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from synapse_memory import status as status_mod

    monkeypatch.setattr(status_mod, "STATUS_FILE", tmp_path / "daily.status.json")
    monkeypatch.setattr(status_mod, "LOCK_FILE", tmp_path / "daily.lock")


def test_steps_are_single_ingest_pipeline() -> None:
    assert STEPS == ("collect_claude_code", "collect_codex", "ingest", "lint")


def test_dry_run_lists_steps(capsys: pytest.CaptureFixture[str]) -> None:
    result = run_daily(dry_run=True)
    out = capsys.readouterr().out

    for stage in STEPS:
        assert f"[x] {stage}" in out
    assert result.steps == []


def test_dry_run_with_only_and_skip(capsys: pytest.CaptureFixture[str]) -> None:
    run_daily(only={"collect_codex", "lint"}, skip={"lint"}, dry_run=True)
    out = capsys.readouterr().out

    assert "[x] collect_codex" in out
    assert "[ ] collect_claude_code" in out
    assert "[ ] ingest" in out
    assert "[ ] lint" in out


def test_stage_validation_rejects_duplicate_and_unknown_dependency() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        validate_daily_stages((DailyStage("a", "A"), DailyStage("a", "B")))

    with pytest.raises(ValueError, match="unknown dependency"):
        validate_daily_stages((DailyStage("a", "A", ("missing",)),))


def test_step_result_status_properties() -> None:
    assert StepResult.skipped("ingest", "requires collect_codex").status == "skipped"
    assert StepResult.skipped("ingest", "requires collect_codex").skip_reason
    assert StepResult.failed("ingest", 1.2, "boom").status == "failed"
    assert StepResult.success("lint", 0.5, "dead_links-=0").ok is True


def test_dependency_failure_skips_downstream() -> None:
    calls: list[str] = []

    def track(name: str, fn):
        def step():
            calls.append(name)
            return fn()

        return step

    result = run_daily(
        stage_actions={
            "collect_claude_code": track("collect_claude_code", _ok("mirrored=0")),
            "collect_codex": track("collect_codex", _fail("collect failed")),
            "ingest": track("ingest", _ok("docs=1")),
            "lint": track("lint", _ok("dead_links-=0")),
        },
        on_log=lambda _line: None,
    )

    by_name = {step.name: step for step in result.steps}
    assert calls == ["collect_claude_code", "collect_codex"]
    assert by_name["collect_codex"].status == StageStatus.FAILED
    assert by_name["ingest"].status == StageStatus.SKIPPED
    assert by_name["ingest"].skip_reason == "requires collect_codex"
    assert by_name["lint"].status == StageStatus.SKIPPED
    assert result.errors == 1
    assert result.skipped == 2


def test_resume_from_ingest_marks_collectors_skipped() -> None:
    calls: list[str] = []

    def track(name: str):
        def step() -> str:
            calls.append(name)
            return f"{name}=ok"

        return step

    result = run_daily(
        resume_from="ingest",
        stage_actions={
            "ingest": track("ingest"),
            "lint": track("lint"),
        },
        on_log=lambda _line: None,
    )

    by_name = {step.name: step for step in result.steps}
    assert calls == ["ingest", "lint"]
    assert by_name["collect_claude_code"].status == StageStatus.SKIPPED
    assert by_name["collect_codex"].skip_reason == "resume before ingest"
    assert by_name["ingest"].status == StageStatus.SUCCESS


def test_unknown_stage_names_raise_before_execution() -> None:
    with pytest.raises(ValueError, match="unknown daily stage"):
        run_daily(resume_from="nope", dry_run=True)
    with pytest.raises(ValueError, match="unknown daily stage in only"):
        run_daily(only={"nope"}, dry_run=True)
    with pytest.raises(ValueError, match="unknown daily stage in skip"):
        run_daily(skip={"nope"}, dry_run=True)


def test_only_stage_without_dependency_is_skipped() -> None:
    calls: list[str] = []

    def ingest() -> str:
        calls.append("ingest")
        return "docs=1"

    result = run_daily(
        only={"ingest"},
        stage_actions={"ingest": ingest},
        on_log=lambda _line: None,
    )

    assert calls == []
    assert [(s.name, s.status, s.skip_reason) for s in result.steps] == [
        ("ingest", StageStatus.SKIPPED, "requires collect_claude_code")
    ]


def test_build_stage_actions_exposes_single_pipeline_actions() -> None:
    actions = _build_stage_actions(on_log=lambda _line: None, ingest_model=None)

    assert set(actions) == set(STEPS)
    assert callable(actions["ingest"])


def test_run_daily_resolves_card_generate_model_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {}

    def fake_actions(
        *,
        ingest_model: str | None = None,
        on_log: object,
        status_sink: object = None,
        result: object = None,
    ) -> dict[str, object]:
        captured["ingest_model"] = ingest_model
        return {stage: _ok(f"{stage}=ok") for stage in STEPS}

    monkeypatch.setattr(
        ai_api,
        "resolve_model_for_task",
        lambda task: "gpt-5.6-terra" if task == "card_generate" else None,
    )
    monkeypatch.setattr(daily_mod, "_build_stage_actions", fake_actions)

    result = run_daily(on_log=lambda _line: None, acquire_lock=False)

    assert result.errors == 0
    assert captured["ingest_model"] == "gpt-5.6-terra"


def test_run_daily_preserves_explicit_ingest_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {}

    def fake_actions(
        *,
        ingest_model: str | None = None,
        on_log: object,
        status_sink: object = None,
        result: object = None,
    ) -> dict[str, object]:
        captured["ingest_model"] = ingest_model
        return {stage: _ok(f"{stage}=ok") for stage in STEPS}

    monkeypatch.setattr(
        ai_api,
        "resolve_model_for_task",
        lambda _task: pytest.fail("explicit model must not be resolved"),
    )
    monkeypatch.setattr(daily_mod, "_build_stage_actions", fake_actions)

    result = run_daily(
        ingest_model="manual-model",
        on_log=lambda _line: None,
        acquire_lock=False,
    )

    assert result.errors == 0
    assert captured["ingest_model"] == "manual-model"


def test_successful_stage_errors_are_counted_as_warnings() -> None:
    result = run_daily(
        only={"collect_claude_code"},
        stage_actions={
            "collect_claude_code": _ok("mirrored=0 unchanged=0 bytes+=0 errors=2")
        },
        on_log=lambda _line: None,
    )

    assert result.errors == 0
    assert result.warnings == 2
    text = render_daily_report(result, date="2026-05-18", est_usd=0.0)
    assert "warnings_count: 2" in text


def test_humanize_collectors_and_passthrough() -> None:
    claude = _humanize_stage_summary(
        "collect_claude_code",
        "scanned=5 mirrored=3 bytes+=1024 truncations=2 skipped_empty=1 errors=1",
    )
    codex = _humanize_stage_summary(
        "collect_codex",
        "scanned=10 mirrored=3 bytes+=2048 truncations=0 skipped_empty=0 errors=0",
    )

    assert "Claude 활동 로그 3개 mirror" in claude
    assert "잘림 2" in claude
    assert "Codex 활동 로그 3개 mirror" in codex
    assert _humanize_stage_summary("ingest", "docs=1 pages=1") == "docs=1 pages=1"
