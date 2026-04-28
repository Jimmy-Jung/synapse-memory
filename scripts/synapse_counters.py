#!/usr/bin/env python3
"""
Synapse pipeline counters.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_COUNTER_DIR = Path.home() / ".synapse" / "counters"
SCHEMA_VERSION = "SynapseCounters-v1"
STAGES = (
    "claude_collector",
    "codex_collector",
    "extractor",
    "inbox_writer",
    "reviewer",
)
FIELDS = ("success", "drop", "dup", "error", "blocked")


class CounterError(Exception):
    """Raised when a counter update is invalid."""


def utc_today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def empty_stage() -> dict[str, Any]:
    return {
        "success": 0,
        "drop": 0,
        "dup": 0,
        "error": 0,
        "blocked": 0,
        "latency_ms": {"count": 0, "sum": 0, "max": 0},
    }


def empty_counter(date_utc: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "date_utc": date_utc,
        "stages": {stage: empty_stage() for stage in STAGES},
    }


def counter_path(base_dir: Path | None = None, date_utc: str | None = None) -> Path:
    base = (base_dir or DEFAULT_COUNTER_DIR).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{date_utc or utc_today()}.json"


def _read_unlocked(path: Path, date_utc: str) -> dict[str, Any]:
    if not path.exists():
        return empty_counter(date_utc)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise CounterError(f"invalid counter file: {path}")
    stages = data.setdefault("stages", {})
    for stage in STAGES:
        stages.setdefault(stage, empty_stage())
    return data


def update(
    stage: str,
    field: str,
    *,
    amount: int = 1,
    latency_ms: int | None = None,
    base_dir: Path | None = None,
    date_utc: str | None = None,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise CounterError(f"unknown stage: {stage}")
    if field not in FIELDS:
        raise CounterError(f"unknown counter field: {field}")
    if amount < 0:
        raise CounterError("amount must be non-negative")
    if latency_ms is not None and latency_ms < 0:
        raise CounterError("latency_ms must be non-negative")

    date_text = date_utc or utc_today()
    path = counter_path(base_dir, date_text)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = _read_unlocked(path, date_text)
            stage_data = data["stages"][stage]
            stage_data[field] += amount
            if latency_ms is not None:
                latency = stage_data["latency_ms"]
                latency["count"] += 1
                latency["sum"] += latency_ms
                latency["max"] = max(latency["max"], latency_ms)

            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return data


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Update Synapse daily counters")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("field", choices=FIELDS)
    parser.add_argument("--amount", type=int, default=1)
    parser.add_argument("--latency-ms", type=int)
    args = parser.parse_args(argv)
    data = update(args.stage, args.field, amount=args.amount, latency_ms=args.latency_ms)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
