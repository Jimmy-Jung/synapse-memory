"""Cost event summary aggregation and rendering."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, TypeAlias

from synapse_memory.cost.events import CostEvent, load_cost_events

SummaryBy: TypeAlias = Literal["command", "model"]


@dataclass(frozen=True)
class CostSummaryGroup:
    group: str
    calls: int
    input_tokens: int
    output_tokens: int
    usd: float
    elapsed_s: float
    first_seen: str | None
    last_seen: str | None


@dataclass(frozen=True)
class CostSummary:
    days: int
    by: SummaryBy
    generated_at: str
    groups: list[CostSummaryGroup]
    total: CostSummaryGroup


def load_summary(
    *,
    days: int = 30,
    by: SummaryBy = "command",
    path: Path | None = None,
    now: datetime | None = None,
) -> CostSummary:
    events = load_cost_events(path=path, recover=True)
    return summarize_costs(events, days=days, by=by, now=now)


def summarize_costs(
    events: list[CostEvent],
    *,
    days: int = 30,
    by: SummaryBy = "command",
    now: datetime | None = None,
) -> CostSummary:
    if days < 1:
        raise ValueError("--days must be >= 1")
    resolved_now = now or datetime.now(UTC)
    cutoff = resolved_now - timedelta(days=days)
    grouped: dict[str, list[CostEvent]] = {}
    for event in events:
        event_ts = _parse_ts(event.ts)
        if event_ts < cutoff or event_ts > resolved_now:
            continue
        key = event.command if by == "command" else event.model
        grouped.setdefault(key, []).append(event)

    groups = [
        _build_group(key, sorted(items, key=lambda e: e.ts))
        for key, items in sorted(grouped.items())
    ]
    total = _build_group("TOTAL", sorted((e for items in grouped.values() for e in items), key=lambda e: e.ts))
    return CostSummary(
        days=days,
        by=by,
        generated_at=resolved_now.isoformat().replace("+00:00", "Z"),
        groups=groups,
        total=total,
    )


def render_summary_table(summary: CostSummary) -> str:
    if summary.total.calls == 0:
        return "데이터 없음 — 아직 기록된 cost event 가 없습니다."

    lines = [
        f"Cost summary (last {summary.days} days, by {summary.by})",
        f"{'GROUP':<24} {'CALLS':>6} {'INPUT':>8} {'OUTPUT':>8} {'USD':>10} {'ELAPSED':>10}",
    ]
    for group in summary.groups:
        lines.append(_format_group(group))
    lines.append(_format_group(summary.total))
    return "\n".join(lines)


def render_summary_json(summary: CostSummary) -> str:
    payload = {
        "days": summary.days,
        "by": summary.by,
        "generated_at": summary.generated_at,
        "total": _group_to_json(summary.total),
        "groups": [_group_to_json(group) for group in summary.groups],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _build_group(group: str, events: list[CostEvent]) -> CostSummaryGroup:
    return CostSummaryGroup(
        group=group,
        calls=len(events),
        input_tokens=sum(e.input_tokens for e in events),
        output_tokens=sum(e.output_tokens for e in events),
        usd=round(sum(e.usd for e in events), 8),
        elapsed_s=round(sum(e.elapsed_s for e in events), 4),
        first_seen=events[0].ts if events else None,
        last_seen=events[-1].ts if events else None,
    )


def _format_group(group: CostSummaryGroup) -> str:
    return (
        f"{group.group:<24} {group.calls:>6} {group.input_tokens:>8} "
        f"{group.output_tokens:>8} {group.usd:>10.4f} {group.elapsed_s:>9.1f}s"
    )


def _group_to_json(group: CostSummaryGroup) -> dict[str, object]:
    return asdict(group)


def _parse_ts(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
