#!/usr/bin/env python3
"""
Bootstrap local Synapse Memory runtime directories on a new Mac.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
from pathlib import Path
from typing import Any


SYNAPSE_ROOT = Path.home() / ".synapse"
PRIVATE_ROOT = SYNAPSE_ROOT / "private"
COUNTERS_DIR = SYNAPSE_ROOT / "counters"
BIN_DIR = SYNAPSE_ROOT / "bin"
LOGS_DIR = SYNAPSE_ROOT / "logs"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"


def utc_today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def required_dirs(root: Path = SYNAPSE_ROOT) -> list[Path]:
    private = root / "private"
    return [
        root / "bin",
        root / "counters",
        root / "logs",
        private / "queue",
        private / "checkpoints",
        private / "backups",
        private / "dead-letter",
        private / "normalized" / "claude",
        private / "normalized" / "codex",
        private / "redaction-reports",
        private / "fixtures",
    ]


def private_readme() -> str:
    return """---
title: Synapse Private Store
author: JunyoungJung
---

# Synapse Private Store

This directory is local-only runtime state for Synapse Memory.

Do not sync this directory to iCloud, Dropbox, Git, or any shared Vault.
"""


def empty_counters(date_utc: str) -> dict[str, Any]:
    stage = {"success": 0, "drop": 0, "dup": 0, "error": 0, "blocked": 0, "latency_ms": {"count": 0, "sum": 0, "max": 0}}
    return {
        "schema_version": "SynapseCounters-v1",
        "date_utc": date_utc,
        "stages": {
            "claude_collector": dict(stage),
            "codex_collector": dict(stage),
            "extractor": dict(stage),
            "inbox_writer": dict(stage),
            "reviewer": dict(stage),
        },
    }


def bootstrap(*, root: Path = SYNAPSE_ROOT, settings_file: Path = SETTINGS_FILE, apply: bool = False) -> dict[str, Any]:
    dirs = required_dirs(root)
    private_root = root / "private"
    counters_dir = root / "counters"
    readme_path = private_root / "README.md"
    counter_path = counters_dir / f"{utc_today()}.json"
    backup_path = private_root / "backups" / f"settings.json.{utc_stamp()}"

    result: dict[str, Any] = {
        "apply": apply,
        "directories": [str(path) for path in dirs],
        "private_readme": str(readme_path),
        "counter": str(counter_path),
        "settings_backup": str(backup_path) if settings_file.exists() else None,
    }
    if not apply:
        return result

    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
    if not readme_path.exists():
        readme_path.write_text(private_readme(), encoding="utf-8")
    if not counter_path.exists():
        counter_path.write_text(json.dumps(empty_counters(utc_today()), ensure_ascii=False, indent=2), encoding="utf-8")
    if settings_file.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings_file, backup_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Synapse Memory local runtime")
    parser.add_argument("--apply", action="store_true", help="create directories and initial files")
    parser.add_argument("--dry-run", action="store_true", help="show planned changes")
    args = parser.parse_args(argv)
    result = bootstrap(apply=args.apply and not args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
