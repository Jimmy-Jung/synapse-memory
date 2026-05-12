"""Cost CLI tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import synapse_memory.cli as cli_mod
from synapse_memory.cli import cmd_cost_summary
from synapse_memory.cost.events import append_cost_event, build_cost_event
from synapse_memory.storage.l0 import L0_ENV_VAR


def _args(**overrides: object) -> argparse.Namespace:
    data = {"days": 30, "by": "command", "json": False}
    data.update(overrides)
    return argparse.Namespace(**data)


def test_parser_has_cost_summary_command() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["cost", "summary", "--days", "7", "--by", "model"])

    assert args.func is cmd_cost_summary
    assert args.days == 7
    assert args.by == "model"


def test_cost_summary_no_data_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))

    rc = cmd_cost_summary(_args())

    assert rc == 0
    assert "데이터 없음" in capsys.readouterr().out


def test_cost_summary_json_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    append_cost_event(
        build_cost_event(
            command="ask",
            provider="claude",
            model="sonnet",
            status="success",
            input_tokens=10,
            output_tokens=5,
            usd=0.1,
            pricing_source="estimated",
            elapsed_s=1.0,
            now=datetime.now(UTC),
        )
    )

    rc = cmd_cost_summary(_args(json=True))

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total"]["calls"] == 1


def test_cost_summary_invalid_days(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_cost_summary(_args(days=0))

    assert rc == 1
    assert "--days must be >= 1" in capsys.readouterr().err
