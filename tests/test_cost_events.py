"""Cost event storage tests.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse_memory.cost.events import (
    CostEvent,
    append_cost_event,
    build_cost_event,
    command_context,
    current_command,
    load_cost_events,
)
from synapse_memory.cost.pricing import price_usage
from synapse_memory.storage.l0 import L0_ENV_VAR


def test_build_cost_event_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="command"):
        build_cost_event(
            command="",
            provider="claude",
            model="sonnet",
            status="success",
            input_tokens=1,
            output_tokens=1,
            usd=0.0,
            pricing_source="estimated",
            elapsed_s=0.1,
        )


def test_build_cost_event_rejects_negative_numbers() -> None:
    with pytest.raises(ValueError, match="input_tokens"):
        build_cost_event(
            command="ask",
            provider="claude",
            model="sonnet",
            status="success",
            input_tokens=-1,
            output_tokens=1,
            usd=0.0,
            pricing_source="estimated",
            elapsed_s=0.1,
        )


def test_cost_event_from_dict_rejects_prohibited_fields() -> None:
    data = build_cost_event(
        command="ask",
        provider="claude",
        model="sonnet",
        status="success",
        input_tokens=10,
        output_tokens=5,
        usd=0.001,
        pricing_source="estimated",
        elapsed_s=1.2,
    ).to_dict()
    data["prompt"] = "내 이름은 홍길동"

    with pytest.raises(ValueError, match="prohibited"):
        CostEvent.from_dict(data)


def test_append_and_load_cost_events_secure_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    event = build_cost_event(
        command="ask",
        provider="claude",
        model="sonnet",
        status="success",
        input_tokens=10,
        output_tokens=5,
        usd=0.001,
        pricing_source="estimated",
        elapsed_s=1.2,
    )

    path = append_cost_event(event)
    loaded = load_cost_events()

    assert loaded == [event]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_load_cost_events_recovers_corrupt_tail(tmp_path: Path) -> None:
    path = tmp_path / "cost.jsonl"
    event = build_cost_event(
        command="ask",
        provider="claude",
        model="sonnet",
        status="success",
        input_tokens=10,
        output_tokens=5,
        usd=0.001,
        pricing_source="estimated",
        elapsed_s=1.2,
        now=datetime(2026, 5, 12, tzinfo=UTC),
    )
    path.write_text(
        json.dumps(event.to_dict(), ensure_ascii=False) + "\n{bad json\n",
        encoding="utf-8",
    )

    loaded = load_cost_events(path=path, recover=True)

    assert loaded == [event]
    assert path.read_text(encoding="utf-8").count("\n") == 1
    backups = list(tmp_path.glob("cost.jsonl.bak.*"))
    assert len(backups) == 1
    assert "{bad json" in backups[0].read_text(encoding="utf-8")


def test_command_context_restores_previous_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_COMMAND", "outer")

    with command_context("ask"):
        assert current_command() == "ask"

    assert current_command() == "outer"


def test_price_usage_unknown_when_no_provider_cost() -> None:
    priced = price_usage(
        provider="codex",
        model="gpt-5",
        input_tokens=100,
        output_tokens=50,
    )

    assert priced.usd == 0.0
    assert priced.pricing_source == "unknown"

