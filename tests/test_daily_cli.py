"""Daily CLI resilience tests.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse
from pathlib import Path

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
        "dry_run": False,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_parser_has_daily_resume_from() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["daily", "--resume-from", "classify"])

    assert args.func is cmd_daily
    assert args.resume_from == "classify"


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
    assert "건너뜀: 1" in out
    assert "requires classify" in out


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


def test_ci_workflow_exists() -> None:
    assert Path(".github/workflows/ci.yml").is_file()


def test_ci_workflow_runs_required_gates() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python3 -m pytest tests/ -W ignore::DeprecationWarning" in text
    assert "python3 -m ruff check" in text
    assert "python3 -m mypy --strict" in text
    assert "ANTHROPIC_API_KEY" not in text
