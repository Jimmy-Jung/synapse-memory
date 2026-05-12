"""Cost summary tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from synapse_memory.cost.events import append_cost_event, build_cost_event
from synapse_memory.cost.summary import render_summary_json, render_summary_table, summarize_costs


def _event(
    command: str,
    model: str,
    *,
    day: int,
    input_tokens: int,
    output_tokens: int,
    usd: float,
):
    return build_cost_event(
        command=command,
        provider="claude",
        model=model,
        status="success",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usd=usd,
        pricing_source="estimated",
        elapsed_s=1.0,
        now=datetime(2026, 5, day, 12, tzinfo=UTC),
    )


def test_summarize_filters_by_days_and_groups_by_command() -> None:
    events = [
        _event("ask", "sonnet", day=12, input_tokens=10, output_tokens=5, usd=0.1),
        _event("ask", "sonnet", day=11, input_tokens=20, output_tokens=8, usd=0.2),
        _event("daily.generate", "haiku", day=1, input_tokens=999, output_tokens=999, usd=9),
    ]

    summary = summarize_costs(
        events,
        days=2,
        by="command",
        now=datetime(2026, 5, 12, 12, tzinfo=UTC),
    )

    assert len(summary.groups) == 1
    assert summary.groups[0].group == "ask"
    assert summary.groups[0].calls == 2
    assert summary.total.usd == 0.3
    assert summary.total.input_tokens == 30


def test_summarize_groups_by_model() -> None:
    events = [
        _event("ask", "sonnet", day=12, input_tokens=10, output_tokens=5, usd=0.1),
        _event("daily", "haiku", day=12, input_tokens=20, output_tokens=8, usd=0.2),
    ]

    summary = summarize_costs(
        events,
        days=30,
        by="model",
        now=datetime(2026, 5, 12, 12, tzinfo=UTC),
    )

    assert [g.group for g in summary.groups] == ["haiku", "sonnet"]
    assert summary.total.calls == 2


def test_render_summary_json_is_parseable() -> None:
    summary = summarize_costs(
        [_event("ask", "sonnet", day=12, input_tokens=10, output_tokens=5, usd=0.1)],
        days=30,
        by="command",
        now=datetime(2026, 5, 12, 12, tzinfo=UTC),
    )

    data = json.loads(render_summary_json(summary))

    assert data["by"] == "command"
    assert data["total"]["calls"] == 1
    assert "GROUP" not in render_summary_json(summary)


def test_render_summary_table_includes_total() -> None:
    summary = summarize_costs(
        [_event("ask", "sonnet", day=12, input_tokens=10, output_tokens=5, usd=0.1)],
        days=30,
        by="command",
        now=datetime(2026, 5, 12, 12, tzinfo=UTC),
    )

    table = render_summary_table(summary)

    assert "Cost summary" in table
    assert "ask" in table
    assert "TOTAL" in table


def test_summary_loader_recovers_corrupt_tail(tmp_path: Path) -> None:
    path = tmp_path / "cost.jsonl"
    append_cost_event(
        _event("ask", "sonnet", day=12, input_tokens=10, output_tokens=5, usd=0.1),
        path=path,
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{bad json\n")

    from synapse_memory.cost.summary import load_summary

    summary = load_summary(
        path=path,
        days=30,
        by="command",
        now=datetime(2026, 5, 12, 12, tzinfo=UTC),
    )

    assert summary.total.calls == 1
    assert list(tmp_path.glob("cost.jsonl.bak.*"))

