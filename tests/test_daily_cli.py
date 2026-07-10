"""Daily CLI tests.

저자: JunyoungJung
작성일: 2026-07-06
"""

from __future__ import annotations

import argparse
from pathlib import Path
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
        "model": None,
        "watch_status": False,
        "status_interval": 2.0,
        "dry_run": False,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_parser_has_daily_resume_from() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["daily", "--resume-from", "ingest"])

    assert args.func is cmd_daily
    assert args.resume_from == "ingest"


def test_parser_has_daily_model() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["daily", "--model", "gpt-5.5"])

    assert args.func is cmd_daily
    assert args.model == "gpt-5.5"


def test_parser_has_daily_watch_status() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(
        ["daily", "--watch-status", "--status-interval", "0.75"]
    )

    assert args.func is cmd_daily
    assert args.watch_status is True
    assert args.status_interval == 0.75


def test_resolve_model_prefers_config_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """모델은 스폰되는 provider(config) 기준 — runtime 세션 감지가 이기면
    실행 provider와 모델이 어긋난다(예: codex에 sonnet 전달 → 400).
    runtime 감지는 config가 auto일 때만 사용한다."""
    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    config = argparse.Namespace(
        ai_provider="claude",
        models=argparse.Namespace(
            claude=argparse.Namespace(ask="claude-default"),
            codex=argparse.Namespace(ask="codex-default"),
        ),
    )

    with patch("synapse_memory.config.get_config", return_value=config):
        assert cli_mod._resolve_model(None, "ask") == "claude-default"

    auto_config = argparse.Namespace(
        ai_provider="auto",
        models=argparse.Namespace(
            claude=argparse.Namespace(ask="claude-default"),
            codex=argparse.Namespace(ask="codex-default"),
        ),
    )
    with patch("synapse_memory.config.get_config", return_value=auto_config):
        assert cli_mod._resolve_model(None, "ask") == "codex-default"


def test_cmd_daily_prints_failed_and_skipped_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = DailyResult(
        steps=[
            StepResult.success("collect_claude_code", 0.1, "mirrored=0"),
            StepResult.failed("ingest", 1.0, "AI provider 미설치"),
            StepResult.skipped("lint", "requires ingest"),
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
    assert "requires ingest" in out


def test_format_daily_status_line_with_stage_and_item() -> None:
    from synapse_memory.status import DailyStatus

    status = DailyStatus(
        pid=42,
        started_at="2026-05-18T00:00:00+00:00",
        updated_at="2026-05-18T00:00:01+00:00",
        current_stage="ingest",
        current_stage_index=3,
        total_stages=4,
        current_item="codex",
        current_item_index=2,
        current_item_total=2,
    )

    assert (
        cli_mod._format_daily_status_line(status)
        == "[daily-status] ingest (3/4) — codex [2/2, 100%]"
    )


def test_cmd_daily_unknown_resume_returns_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**_kwargs):
        raise ValueError(
            "unknown daily stage: nope\n"
            "valid stages: collect_claude_code, collect_codex, ingest, lint"
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
            only="collect_claude_code, ingest",
            skip="collect_codex, lint",
            dry_run=True,
            model="gpt-5.5",
        )
    )

    assert rc == 0
    assert captured["only"] == {"collect_claude_code", "ingest"}
    assert captured["skip"] == {"collect_codex", "lint"}
    assert captured["ingest_model"] == "gpt-5.5"


def test_cmd_daily_resolves_card_generate_model_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli_mod,
        "_resolve_model",
        lambda model, task: "gpt-5.6-terra" if model is None and task == "card_generate" else model,
    )
    monkeypatch.setattr(
        cli_mod,
        "run_daily",
        lambda **kwargs: captured.update(kwargs) or DailyResult(),
    )

    assert cmd_daily(_args(dry_run=True)) == 0
    assert captured["ingest_model"] == "gpt-5.6-terra"


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
