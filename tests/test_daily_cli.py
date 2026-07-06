"""Daily CLI resilience tests.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import synapse_memory.cli as cli_mod
from synapse_memory.cli import cmd_daily
from synapse_memory.daily import DailyResult, StepResult


def _args(**overrides: object) -> argparse.Namespace:
    data = {
        "only": None,
        "skip": None,
        "resume_from": None,
        "classify_model": "haiku",
        "generate_model": "sonnet",
        "profile_model": "sonnet",
        "profile_sample_lines": 200,
        "profile_facts_only": False,
        "quick": False,
        "quick_days": 7,
        "quick_max_clusters": 10,
        "watch_status": False,
        "status_interval": 2.0,
        "dry_run": False,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_parser_has_daily_resume_from() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["daily", "--resume-from", "classify"])

    assert args.func is cmd_daily
    assert args.resume_from == "classify"


def test_parser_has_daily_watch_status() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(
        ["daily", "--watch-status", "--status-interval", "0.75"]
    )

    assert args.func is cmd_daily
    assert args.watch_status is True
    assert args.status_interval == 0.75


def test_resolve_model_prefers_runtime_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    config = SimpleNamespace(
        ai_provider="claude",
        models=SimpleNamespace(
            claude=SimpleNamespace(classify="haiku"),
            codex=SimpleNamespace(classify="gpt-5.5"),
        ),
    )

    with patch("synapse_memory.config.get_config", return_value=config):
        assert cli_mod._resolve_model(None, "classify") == "gpt-5.5"


def test_cmd_daily_prints_failed_and_skipped_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = DailyResult(
        steps=[
            StepResult.success("collect_claude_code", 0.1, "mirrored=0"),
            StepResult.failed("classify", 1.0, "AI provider 미설치"),
            StepResult.skipped("generate", "requires classify"),
        ],
        total_elapsed=1.1,
    )
    monkeypatch.setattr(cli_mod, "run_daily", lambda **_kwargs: result)

    rc = cmd_daily(_args())

    out = capsys.readouterr().out
    assert rc == 1
    assert "실패: 1" in out
    assert "경고: 0" in out
    assert "건너뜀: 1" in out
    assert "requires classify" in out


def test_format_daily_status_line_with_stage_and_item() -> None:
    from synapse_memory.status import DailyStatus

    status = DailyStatus(
        pid=42,
        started_at="2026-05-18T00:00:00+00:00",
        updated_at="2026-05-18T00:00:01+00:00",
        current_stage="generate",
        current_stage_index=19,
        total_stages=22,
        current_item="project-a",
        current_item_index=3,
        current_item_total=10,
    )

    assert (
        cli_mod._format_daily_status_line(status)
        == "[daily-status] generate (19/22) — project-a [3/10, 30%]"
    )


def test_cmd_daily_unknown_resume_returns_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**_kwargs):
        raise ValueError(
            "unknown daily stage: nope\n"
            "valid stages: collect_claude_code, collect_obsidian, classify"
        )

    monkeypatch.setattr(cli_mod, "run_daily", fail)

    rc = cmd_daily(_args(resume_from="nope"))

    assert rc == 2
    assert "unknown daily stage: nope" in capsys.readouterr().err


def test_cmd_daily_strips_comma_separated_stage_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_daily(**kwargs: object) -> DailyResult:
        captured.update(kwargs)
        return DailyResult()

    monkeypatch.setattr(cli_mod, "run_daily", fake_run_daily)

    rc = cmd_daily(
        _args(
            only="collect_claude_code, report",
            skip="collect_codex, collect_obsidian",
            dry_run=True,
        )
    )

    assert rc == 0
    assert captured["only"] == {"collect_claude_code", "report"}
    assert captured["skip"] == {"collect_codex", "collect_obsidian"}


def test_cmd_daily_unknown_only_returns_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**_kwargs: object) -> DailyResult:
        raise ValueError("unknown daily stage in only: nope")

    monkeypatch.setattr(cli_mod, "run_daily", fail)

    rc = cmd_daily(_args(only="nope"))

    assert rc == 2
    assert "unknown daily stage in only" in capsys.readouterr().err


def test_cmd_daily_already_running_returns_3(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from synapse_memory.status import DailyAlreadyRunningError

    def fail(**_kwargs: object) -> DailyResult:
        raise DailyAlreadyRunningError("daily already running (pid 42)")

    monkeypatch.setattr(cli_mod, "run_daily", fail)

    rc = cmd_daily(_args())

    assert rc == 3
    assert "daily already running" in capsys.readouterr().err


def test_ci_workflow_exists() -> None:
    assert Path(".github/workflows/ci.yml").is_file()


def test_ci_workflow_runs_required_gates() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python3 -m pytest tests/ -W ignore::DeprecationWarning" in text
    assert "python3 -m ruff check" in text
    assert "python3 -m mypy --strict" in text
    assert "ANTHROPIC_API_KEY" not in text
