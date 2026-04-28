#!/usr/bin/env python3
"""
Append pending MemoryCandidate rows to the Synapse MemoryInbox.

Author: JunyoungJung
Date: 2026-04-28

Writes only to today's MemoryInbox file. Existing rows are never modified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_queue as queue


AI_ROOT = SCRIPT_DIR.parent
DEFAULT_INBOX_DIR = AI_ROOT / "MemoryInbox"
DEFAULT_QUEUE_DIR = Path.home() / ".synapse" / "private" / "queue"
KST = dt.timezone(dt.timedelta(hours=9), name="KST")


class InboxWriterError(Exception):
    """Raised when inbox input is invalid."""


def today_kst() -> dt.date:
    return dt.datetime.now(KST).date()


def frontmatter(date_value: dt.date) -> str:
    date_text = date_value.isoformat()
    return f"""---
title: Memory Inbox {date_text}
date: {date_text}
category: System/AI
author: jimmy
tags:
  - synapse
  - ai-memory
  - inbox
  - dom/meta
  - type/system
---

# Memory Inbox {date_text}

| Candidate ID | Source | Candidate | Confidence | Risk | Status | Decision |
|---|---|---|---:|---|---|---|
"""


def load_candidates(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InboxWriterError("candidate input must be JSON") from exc
    if not isinstance(data, list):
        raise InboxWriterError("candidate input must be a list")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise InboxWriterError(f"candidates[{index}] must be an object")
    return data


def candidate_ids_in_text(text: str) -> set[str]:
    ids: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^\|\s*(MC-[^|\s]+)\s*\|", line)
        if match:
            ids.add(match.group(1))
    return ids


def markdown_cell(value: Any) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n+", "<br>", text)
    text = text.replace("|", r"\|")
    return text.strip()


def validate_candidate(candidate: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "candidate_id",
        "source",
        "source_session_id",
        "candidate",
        "confidence",
        "risk",
        "status",
    )
    for field in required:
        if field not in candidate:
            raise InboxWriterError(f"candidate missing required field: {field}")
    if candidate["schema_version"] != "MemoryCandidate-v1":
        raise InboxWriterError(f"unsupported schema_version: {candidate['schema_version']}")
    if candidate["status"] != "pending":
        raise InboxWriterError("automated writer only accepts pending candidates")


def candidate_row(candidate: dict[str, Any]) -> str:
    validate_candidate(candidate)
    source = f"{candidate['source']} / {candidate['source_session_id']}"
    confidence = candidate["confidence"]
    if isinstance(confidence, float):
        confidence_text = f"{confidence:.2f}".rstrip("0").rstrip(".")
    else:
        confidence_text = str(confidence)
    decision_parts = []
    for key in ("memory_type", "ttl", "evidence"):
        value = candidate.get(key)
        if value:
            decision_parts.append(f"{key}={value}")
    decision_text = "; ".join(decision_parts)
    return (
        f"| {markdown_cell(candidate['candidate_id'])} "
        f"| {markdown_cell(source)} "
        f"| {markdown_cell(candidate['candidate'])} "
        f"| {markdown_cell(confidence_text)} "
        f"| {markdown_cell(candidate['risk'])} "
        f"| {markdown_cell(candidate['status'])} "
        f"| {markdown_cell(decision_text)} |\n"
    )


def ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def build_inbox_text(
    existing_text: str | None,
    candidates: list[dict[str, Any]],
    date_value: dt.date,
) -> tuple[str, int]:
    base = existing_text if existing_text is not None else frontmatter(date_value)
    base = ensure_trailing_newline(base)
    existing_ids = candidate_ids_in_text(base)

    rows: list[str] = []
    for candidate in candidates:
        validate_candidate(candidate)
        candidate_id = str(candidate["candidate_id"])
        if candidate_id in existing_ids:
            continue
        existing_ids.add(candidate_id)
        rows.append(candidate_row(candidate))

    if not rows:
        return base, 0
    return base + "".join(rows), len(rows)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def enqueue_retry_payload(
    *,
    path: Path,
    candidates: list[dict[str, Any]],
    reason: str,
    queue_dir: Path,
) -> None:
    queue.enqueue(
        "inbox-retry",
        {
            "target_path": str(path),
            "candidates": candidates,
            "reason": reason,
        },
        queue_dir=queue_dir,
    )


def write_inbox(
    candidates: list[dict[str, Any]],
    *,
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    date_value: dt.date | None = None,
    dry_run: bool = False,
    retries: int = 3,
    backoff_seconds: float = 5.0,
    queue_dir: Path = DEFAULT_QUEUE_DIR,
) -> dict[str, Any]:
    target_date = date_value or today_kst()
    path = inbox_dir / f"{target_date.isoformat()}.md"
    existing_text = path.read_text(encoding="utf-8") if path.exists() else None
    new_text, appended = build_inbox_text(existing_text, candidates, target_date)

    summary = {
        "path": str(path),
        "appended": appended,
        "skipped": len(candidates) - appended,
        "dry_run": dry_run,
    }
    if dry_run or appended == 0:
        return summary

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            atomic_write(path, new_text)
            return summary
        except OSError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_seconds)

    reason = str(last_error) if last_error is not None else "unknown write failure"
    enqueue_retry_payload(path=path, candidates=candidates, reason=reason, queue_dir=queue_dir)
    summary["queued_for_retry"] = True
    summary["reason"] = reason
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append MemoryCandidate rows to MemoryInbox")
    parser.add_argument("--candidates-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    raw = (
        args.candidates_file.read_text(encoding="utf-8")
        if args.candidates_file is not None
        else sys.stdin.read()
    )
    try:
        candidates = load_candidates(raw)
        result = write_inbox(candidates, dry_run=args.dry_run)
    except (InboxWriterError, OSError, json.JSONDecodeError) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
