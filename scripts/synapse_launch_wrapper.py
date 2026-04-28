#!/usr/bin/env python3
"""
LaunchAgent command wrapper with stderr logging and notification.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def notify(label: str, message: str, *, dry_run: bool = False) -> bool:
    if dry_run:
        return False
    osascript = shutil.which("osascript")
    if not osascript:
        return False
    subprocess.run(
        [
            osascript,
            "-e",
            f'display notification "{message[:160]}" with title "Synapse {label}"',
        ],
        check=False,
    )
    return True


def run_wrapped(
    command: list[str],
    *,
    label: str,
    stdout_path: Path,
    stderr_path: Path,
    dry_run: bool = False,
) -> int:
    if dry_run:
        append_log(stdout_path, f"[{utc_now()}] DRY-RUN {label}: {' '.join(command)}\n")
        return 0

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.stdout:
        append_log(stdout_path, completed.stdout)
    if completed.stderr:
        append_log(stderr_path, completed.stderr)
    if completed.returncode != 0:
        marker = f"[{utc_now()}] {label} exited {completed.returncode}\n"
        append_log(stderr_path, marker)
        notify(label, f"exit {completed.returncode}: {completed.stderr.strip() or 'no stderr'}")
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wrap a Synapse LaunchAgent command")
    parser.add_argument("--label", required=True)
    parser.add_argument("--stdout-path", type=Path, required=True)
    parser.add_argument("--stderr-path", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("missing wrapped command", file=sys.stderr)
        return 64
    return run_wrapped(
        command,
        label=args.label,
        stdout_path=args.stdout_path,
        stderr_path=args.stderr_path,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
