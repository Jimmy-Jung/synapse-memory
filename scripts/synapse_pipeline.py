#!/usr/bin/env python3
"""
Phase 3 trigger runner for Synapse AI Memory.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_collect_claude as claude_collector
import synapse_collect_codex as codex_collector
import synapse_counters as counters
import synapse_extract_candidates as extractor
import synapse_inbox_writer as inbox_writer
import synapse_inbox_review as inbox_review
import synapse_memory_guard as guard
import synapse_queue as queue
import synapse_config as config


PRIVATE_ROOT = Path.home() / ".synapse" / "private"
DEFAULT_QUEUE_DIR = PRIVATE_ROOT / "queue"
DEFAULT_DLQ_DIR = PRIVATE_ROOT / "dead-letter"
DEFAULT_CHECKPOINT_DIR = PRIVATE_ROOT / "checkpoints"
DEFAULT_NORMALIZED_DIR = PRIVATE_ROOT / "normalized"
DEFAULT_LOG_DIR = Path.home() / ".synapse" / "logs"
DEFAULT_CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
CLAUDE_QUEUE = "claude-session-end"
EXTRACTOR_CHECKPOINT = "extractor"


class PipelineError(Exception):
    """Raised for recoverable pipeline failures."""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def log_line(message: str, *, log_dir: Path = DEFAULT_LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    line = f"[{utc_now()}] {message}\n"
    with (log_dir / "synapse-pipeline.log").open("a", encoding="utf-8") as handle:
        handle.write(line)


def is_under(path: Path, prefix: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(prefix.expanduser().resolve())
    except ValueError:
        return False
    return True


def extract_transcript_path(payload: dict[str, Any]) -> str | None:
    value = payload.get("transcript_path") or payload.get("transcriptPath")
    if isinstance(value, str) and value.strip():
        return value
    return None


def enqueue_claude_session_end(
    stdin_text: str,
    *,
    queue_dir: Path = DEFAULT_QUEUE_DIR,
    dlq_dir: Path = DEFAULT_DLQ_DIR,
    projects_root: Path = DEFAULT_CLAUDE_PROJECTS_ROOT,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> int:
    """Claude SessionEnd hook entrypoint. Always returns 0."""
    try:
        payload = json.loads(stdin_text or "{}")
        if not isinstance(payload, dict):
            raise PipelineError("payload must be a JSON object")
        transcript = extract_transcript_path(payload)
        if transcript is None:
            raise PipelineError("missing transcript_path")
        transcript_path = Path(transcript).expanduser().resolve()
        if not transcript_path.is_file() or not os.access(transcript_path, os.R_OK):
            raise PipelineError(f"transcript_path is not readable: {transcript_path}")
        if not is_under(transcript_path, projects_root):
            raise PipelineError(f"transcript_path outside Claude projects: {transcript_path}")

        queue.enqueue(
            CLAUDE_QUEUE,
            {
                "transcript_path": str(transcript_path),
                "session_id": payload.get("session_id"),
                "reason": payload.get("reason"),
                "cwd": payload.get("cwd"),
                "hook_event_name": payload.get("hook_event_name"),
            },
            queue_dir=queue_dir,
            dlq_dir=dlq_dir,
        )
        return 0
    except Exception as exc:
        message = f"SessionEnd hook skipped: {type(exc).__name__}: {exc}"
        print(message, file=sys.stderr)
        log_line(message, log_dir=log_dir)
        return 0


def stage_checkpoint_path(stage: str, checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR) -> Path:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir / f"{stage}.json"


def load_stage_checkpoint(stage: str, checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR) -> dict[str, Any]:
    path = stage_checkpoint_path(stage, checkpoint_dir)
    if not path.exists():
        return {"schema_version": "StageCheckpoint-v1", "stage": stage, "items_seen": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "StageCheckpoint-v1":
        raise PipelineError(f"invalid stage checkpoint: {path}")
    if data.get("stage") != stage:
        raise PipelineError(f"stage checkpoint mismatch: {path}")
    if not isinstance(data.get("items_seen"), list):
        raise PipelineError(f"stage checkpoint items_seen invalid: {path}")
    return data


def save_stage_checkpoint(
    stage: str,
    item_id: str,
    *,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    limit: int = 4096,
) -> None:
    path = stage_checkpoint_path(stage, checkpoint_dir)
    data = load_stage_checkpoint(stage, checkpoint_dir)
    items = [str(item) for item in data.get("items_seen", [])]
    if item_id not in items:
        items.append(item_id)
    data["items_seen"] = items[-limit:]
    data["last_run_at"] = utc_now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def has_stage_seen(stage: str, item_id: str, checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR) -> bool:
    try:
        data = load_stage_checkpoint(stage, checkpoint_dir)
    except PipelineError:
        return False
    return item_id in data.get("items_seen", [])


def run_claude_collector(
    *,
    queue_dir: Path = DEFAULT_QUEUE_DIR,
    dlq_dir: Path = DEFAULT_DLQ_DIR,
    out_dir: Path = claude_collector.DEFAULT_OUT_DIR,
    report_dir: Path = claude_collector.DEFAULT_REPORT_DIR,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    projects_root: Path = DEFAULT_CLAUDE_PROJECTS_ROOT,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    items = list(queue.peek(CLAUDE_QUEUE, queue_dir=queue_dir, dlq_dir=dlq_dir)) if dry_run else queue.drain(CLAUDE_QUEUE, queue_dir=queue_dir, dlq_dir=dlq_dir)
    summary: dict[str, Any] = {"processed": [], "skipped": [], "errors": [], "dry_run": dry_run}

    for item in items:
        try:
            transcript = item.get("transcript_path")
            if not isinstance(transcript, str) or not transcript:
                raise PipelineError("queue item missing transcript_path")
            output = claude_collector.collect_file(
                Path(transcript),
                out_dir,
                report_dir,
                require_prefix=projects_root,
                dry_run=dry_run,
                use_checkpoint=True,
                checkpoint_base_dir=checkpoint_dir,
            )
            if output is None:
                summary["skipped"].append(item)
            else:
                summary["processed"].append(str(output))
        except guard.RedactionBlockedError as exc:
            summary["errors"].append({"item": item, "reason": f"RedactionBlockedError: {exc}"})
            if not dry_run:
                queue.dead_letter(CLAUDE_QUEUE, item, reason=str(exc), queue_dir=queue_dir, dlq_dir=dlq_dir)
        except Exception as exc:
            summary["errors"].append({"item": item, "reason": f"{type(exc).__name__}: {exc}"})
            if not dry_run:
                queue.dead_letter(CLAUDE_QUEUE, item, reason=str(exc), queue_dir=queue_dir, dlq_dir=dlq_dir)

    latency_ms = int((time.monotonic() - started) * 1000)
    if not dry_run:
        field = "error" if summary["errors"] else "success"
        counters.update("claude_collector", field, amount=max(1, len(items)), latency_ms=latency_ms)
    return summary


def run_codex_poller(
    *,
    index_path: Path = codex_collector.DEFAULT_INDEX,
    sessions_dir: Path = codex_collector.DEFAULT_SESSIONS_DIR,
    out_dir: Path = codex_collector.DEFAULT_OUT_DIR,
    report_dir: Path = codex_collector.DEFAULT_REPORT_DIR,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    days: int = codex_collector.DEFAULT_RECENT_DAYS,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    result = codex_collector.collect_recent(
        index_path=index_path,
        sessions_dir=sessions_dir,
        out_dir=out_dir,
        report_dir=report_dir,
        days=days,
        backfill=False,
        dry_run=dry_run,
        use_checkpoint=True,
        checkpoint_base_dir=checkpoint_dir,
    )
    if not dry_run:
        field = "error" if result["errors"] else "success"
        amount = max(1, len(result["processed"]) + len(result["skipped"]) + len(result["errors"]))
        counters.update("codex_collector", field, amount=amount, latency_ms=int((time.monotonic() - started) * 1000))
    return result


def session_item_id(record_path: Path, record: dict[str, Any]) -> str:
    return ":".join(
        [
            str(record.get("source", "")),
            str(record.get("source_session_id", "")),
            str(record.get("content_hash", "")),
            guard.sha256_text(str(record_path)),
        ]
    )


def iter_session_records(normalized_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for source in ("claude", "codex"):
        source_dir = normalized_dir / source
        if source_dir.is_dir():
            paths.extend(sorted(source_dir.glob("*.json")))
    return sorted(paths)


def run_extractor(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    inbox_dir: Path | None = None,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    queue_dir: Path = DEFAULT_QUEUE_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    summary: dict[str, Any] = {
        "processed": [],
        "skipped": [],
        "errors": [],
        "candidates": 0,
        "dry_run": dry_run,
    }

    for path in iter_session_records(normalized_dir):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise PipelineError("SessionRecord JSON must be an object")
            item_id = session_item_id(path, record)
            if has_stage_seen(EXTRACTOR_CHECKPOINT, item_id, checkpoint_dir):
                summary["skipped"].append(str(path))
                continue
            candidates = extractor.extract_candidates_from_record(record)
            if not candidates:
                summary["skipped"].append(str(path))
                if not dry_run:
                    save_stage_checkpoint(EXTRACTOR_CHECKPOINT, item_id, checkpoint_dir=checkpoint_dir)
                continue
            if not dry_run:
                inbox_writer.write_inbox(candidates, inbox_dir=inbox_dir or config.memory_inbox_dir(), queue_dir=queue_dir)
                save_stage_checkpoint(EXTRACTOR_CHECKPOINT, item_id, checkpoint_dir=checkpoint_dir)
            summary["processed"].append(str(path))
            summary["candidates"] += len(candidates)
        except guard.RedactionBlockedError as exc:
            summary["errors"].append({"path": str(path), "reason": f"RedactionBlockedError: {exc}"})
        except Exception as exc:
            summary["errors"].append({"path": str(path), "reason": f"{type(exc).__name__}: {exc}"})

    if not dry_run:
        field = "error" if summary["errors"] else "success"
        amount = max(1, len(summary["processed"]) + len(summary["skipped"]) + len(summary["errors"]))
        counters.update("extractor", field, amount=amount, latency_ms=int((time.monotonic() - started) * 1000))
    return summary


def run_reviewer(*, dry_run: bool = False) -> dict[str, Any]:
    return inbox_review.review_inbox(
        inbox_dir=config.memory_inbox_dir(),
        review_path=config.memory_review_path(),
        dry_run=dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synapse Phase 3 pipeline runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("claude-session-end-hook")

    p_collector = sub.add_parser("collector")
    p_collector.add_argument("--dry-run", action="store_true")

    p_codex = sub.add_parser("codex-poller")
    p_codex.add_argument("--dry-run", action="store_true")
    p_codex.add_argument("--days", type=int, default=codex_collector.DEFAULT_RECENT_DAYS)

    p_extract = sub.add_parser("extractor")
    p_extract.add_argument("--dry-run", action="store_true")

    p_review = sub.add_parser("reviewer")
    p_review.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "claude-session-end-hook":
        return enqueue_claude_session_end(sys.stdin.read())
    if args.cmd == "collector":
        print(json.dumps(run_claude_collector(dry_run=args.dry_run), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "codex-poller":
        print(json.dumps(run_codex_poller(days=args.days, dry_run=args.dry_run), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "extractor":
        print(json.dumps(run_extractor(dry_run=args.dry_run), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "reviewer":
        print(json.dumps(run_reviewer(dry_run=args.dry_run), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
