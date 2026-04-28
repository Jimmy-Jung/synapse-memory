#!/usr/bin/env python3
"""
Append daily Synapse counter KPI summary.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any


AI_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COUNTER_DIR = Path.home() / ".synapse" / "counters"
DEFAULT_REVIEW_PATH = AI_ROOT / "MemoryReview.md"


def utc_today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def load_counter(counter_dir: Path = DEFAULT_COUNTER_DIR, date_utc: str | None = None) -> dict[str, Any]:
    date_text = date_utc or utc_today()
    path = counter_dir / f"{date_text}.json"
    if not path.exists():
        return {"schema_version": "SynapseCounters-v1", "date_utc": date_text, "stages": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"counter must be object: {path}")
    return data


def compute_kpi(counter: dict[str, Any]) -> dict[str, Any]:
    totals = {"success": 0, "drop": 0, "dup": 0, "error": 0, "blocked": 0}
    latency_count = 0
    latency_sum = 0
    for stage in counter.get("stages", {}).values():
        if not isinstance(stage, dict):
            continue
        for key in totals:
            totals[key] += int(stage.get(key, 0) or 0)
        latency = stage.get("latency_ms", {})
        if isinstance(latency, dict):
            latency_count += int(latency.get("count", 0) or 0)
            latency_sum += int(latency.get("sum", 0) or 0)
    total_events = sum(totals.values())
    return {
        **totals,
        "total": total_events,
        "success_rate": round(totals["success"] / total_events, 4) if total_events else 0.0,
        "dup_rate": round(totals["dup"] / total_events, 4) if total_events else 0.0,
        "blocked_rate": round(totals["blocked"] / total_events, 4) if total_events else 0.0,
        "avg_latency_ms": round(latency_sum / latency_count, 2) if latency_count else 0.0,
    }


def kpi_line(date_utc: str, kpi: dict[str, Any]) -> str:
    return (
        f"- {date_utc}: KPI success_rate={kpi['success_rate']:.2%} "
        f"dup_rate={kpi['dup_rate']:.2%} blocked_rate={kpi['blocked_rate']:.2%} "
        f"avg_latency_ms={kpi['avg_latency_ms']} total={kpi['total']}\n"
    )


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_kpi(
    *,
    counter_dir: Path = DEFAULT_COUNTER_DIR,
    review_path: Path = DEFAULT_REVIEW_PATH,
    date_utc: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    counter = load_counter(counter_dir, date_utc)
    date_text = str(counter.get("date_utc") or date_utc or utc_today())
    kpi = compute_kpi(counter)
    line = kpi_line(date_text, kpi)
    if not dry_run:
        base = review_path.read_text(encoding="utf-8") if review_path.exists() else "# Memory Review\n\n"
        atomic_write(review_path, base.rstrip() + "\n" + line)
    return {"date_utc": date_text, "dry_run": dry_run, "line": line.strip(), "kpi": kpi}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append Synapse daily KPI summary")
    parser.add_argument("--date-utc")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = append_kpi(date_utc=args.date_utc, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
