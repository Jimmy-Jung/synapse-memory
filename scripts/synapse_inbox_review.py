#!/usr/bin/env python3
"""
Review MemoryInbox candidates without approving them.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_counters as counters


AI_ROOT = SCRIPT_DIR.parent
DEFAULT_INBOX_DIR = AI_ROOT / "MemoryInbox"
DEFAULT_REVIEW_PATH = AI_ROOT / "MemoryReview.md"
KST = dt.timezone(dt.timedelta(hours=9), name="KST")


class InboxReviewError(Exception):
    """Raised when an inbox review cannot be completed."""


def today_kst() -> dt.date:
    return dt.datetime.now(KST).date()


def split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            current.append(char)
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def join_markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def extract_ttl(decision: str) -> dt.date | None:
    match = re.search(r"\bttl\s*[:=]\s*(\d{4}-\d{2}-\d{2})\b", decision)
    if not match:
        return None
    try:
        return dt.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def review_inbox_text(text: str, today: dt.date) -> tuple[str, dict[str, int]]:
    lines = text.splitlines()
    changed = 0
    pending = 0
    expired = 0
    reviewed = 0
    output: list[str] = []

    for line in lines:
        if not line.startswith("| MC-"):
            output.append(line)
            continue
        cells = split_markdown_row(line)
        if len(cells) < 7:
            output.append(line)
            continue
        reviewed += 1
        status = cells[5].strip()
        if status == "pending":
            pending += 1
            ttl = extract_ttl(cells[6])
            if ttl is not None and ttl < today:
                cells[5] = "expired"
                expired += 1
                changed += 1
                line = join_markdown_row(cells)
        output.append(line)

    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(output) + suffix, {
        "reviewed": reviewed,
        "pending": pending,
        "expired": expired,
        "changed": changed,
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_review_summary(review_path: Path, *, today: dt.date, summary: dict[str, int], dry_run: bool) -> None:
    line = (
        f"- {today.isoformat()}: inbox_review reviewed={summary['reviewed']} "
        f"pending={summary['pending']} expired={summary['expired']} changed={summary['changed']}\n"
    )
    if dry_run:
        return
    base = review_path.read_text(encoding="utf-8") if review_path.exists() else "# Memory Review\n\n"
    atomic_write_text(review_path, base.rstrip() + "\n" + line)


def notify_if_many_pending(pending_count: int, *, threshold: int = 5, dry_run: bool = False) -> bool:
    if pending_count < threshold or dry_run:
        return False
    osascript = shutil.which("osascript")
    if not osascript:
        return False
    subprocess.run(
        [
            osascript,
            "-e",
            f'display notification "{pending_count} pending memory candidates" with title "Synapse Memory"',
        ],
        check=False,
    )
    return True


def review_inbox(
    *,
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    review_path: Path = DEFAULT_REVIEW_PATH,
    today: dt.date | None = None,
    dry_run: bool = False,
    update_counters: bool = True,
) -> dict[str, Any]:
    today_value = today or today_kst()
    total = {"reviewed": 0, "pending": 0, "expired": 0, "changed": 0}
    files = sorted(inbox_dir.glob("*.md")) if inbox_dir.exists() else []

    for path in files:
        text = path.read_text(encoding="utf-8")
        new_text, summary = review_inbox_text(text, today_value)
        for key in total:
            total[key] += summary[key]
        if summary["changed"] and not dry_run:
            atomic_write_text(path, new_text)

    notified = notify_if_many_pending(total["pending"], dry_run=dry_run)
    append_review_summary(review_path, today=today_value, summary=total, dry_run=dry_run)
    if not dry_run and update_counters:
        counters.update("reviewer", "success", amount=max(1, len(files)))
    return {**total, "files": len(files), "notified": notified, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review MemoryInbox without auto-approval")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = review_inbox(dry_run=args.dry_run)
    except OSError as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
