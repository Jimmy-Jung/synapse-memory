#!/usr/bin/env python3
"""
Run a local-only Synapse e2e fixture.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_pipeline as pipeline


def dummy_claude_jsonl(path: Path) -> None:
    lines = [
        json.dumps({"type": "system", "sessionId": "e2e-session"}),
        json.dumps(
            {
                "type": "user",
                "sessionId": "e2e-session",
                "timestamp": "2026-04-28T12:00:00Z",
                "uuid": "e2e-1",
                "message": {
                    "role": "user",
                    "content": "기억해줘: 나는 e2e fixture 결과를 간결하게 보는 걸 선호해",
                },
            },
            ensure_ascii=False,
        ),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_e2e_fixture(*, work_dir: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    if work_dir is None:
        with tempfile.TemporaryDirectory() as tmp:
            return run_e2e_fixture(work_dir=Path(tmp), dry_run=dry_run)

    root = work_dir
    projects = root / "claude-projects"
    transcript = projects / "session.jsonl"
    projects.mkdir(parents=True, exist_ok=True)
    dummy_claude_jsonl(transcript)

    queue_dir = root / "queue"
    dlq_dir = root / "dead-letter"
    normalized = root / "normalized" / "claude"
    reports = root / "reports"
    checkpoints = root / "checkpoints"
    inbox = root / "MemoryInbox"
    logs = root / "logs"

    hook_payload = {
        "session_id": "e2e-session",
        "transcript_path": str(transcript),
        "hook_event_name": "SessionEnd",
        "reason": "logout",
        "cwd": str(root),
    }
    pipeline.enqueue_claude_session_end(
        json.dumps(hook_payload),
        queue_dir=queue_dir,
        dlq_dir=dlq_dir,
        projects_root=projects,
        log_dir=logs,
    )
    collector = pipeline.run_claude_collector(
        queue_dir=queue_dir,
        dlq_dir=dlq_dir,
        out_dir=normalized,
        report_dir=reports,
        checkpoint_dir=checkpoints,
        projects_root=projects,
        dry_run=dry_run,
    )
    extractor = pipeline.run_extractor(
        normalized_dir=root / "normalized",
        inbox_dir=inbox,
        checkpoint_dir=checkpoints,
        queue_dir=queue_dir,
        dry_run=dry_run,
    )
    return {
        "dry_run": dry_run,
        "work_dir": str(root),
        "collector": collector,
        "extractor": extractor,
        "inbox_files": sorted(str(path) for path in inbox.glob("*.md")) if inbox.exists() else [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Synapse e2e fixture in a temp workspace")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_e2e_fixture(work_dir=args.work_dir, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
