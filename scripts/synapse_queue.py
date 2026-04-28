#!/usr/bin/env python3
"""
Synapse pipeline queue.

Author: jimmy
Date: 2026-04-28

flock(2) 기반 atomic enqueue/consume + dead-letter. 모든 큐 파일은 JSONL.
한 줄 = 한 작업. 작업은 read-and-truncate 패턴으로 소비된다.

Queue layout:
  ~/.synapse/private/queue/<name>.jsonl       — 활성 큐
  ~/.synapse/private/queue/<name>.lock        — flock 대상
  ~/.synapse/private/dead-letter/<name>.jsonl — 처리 실패 작업
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Iterator


PRIVATE_ROOT = Path.home() / ".synapse" / "private"
DEFAULT_QUEUE_DIR = PRIVATE_ROOT / "queue"
DEFAULT_DLQ_DIR = PRIVATE_ROOT / "dead-letter"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


@dataclasses.dataclass(frozen=True)
class QueuePaths:
    queue: Path
    lock: Path
    dead_letter: Path

    @classmethod
    def for_name(
        cls,
        name: str,
        queue_dir: Path | None = None,
        dlq_dir: Path | None = None,
    ) -> "QueuePaths":
        qdir = (queue_dir or DEFAULT_QUEUE_DIR).expanduser()
        ddir = (dlq_dir or DEFAULT_DLQ_DIR).expanduser()
        qdir.mkdir(parents=True, exist_ok=True)
        ddir.mkdir(parents=True, exist_ok=True)
        return cls(
            queue=qdir / f"{name}.jsonl",
            lock=qdir / f"{name}.lock",
            dead_letter=ddir / f"{name}.jsonl",
        )


class _FileLock:
    """flock(2) wrapper. exclusive lock 기본."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: Any = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if self._handle is not None:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            if self._handle is not None:
                self._handle.close()
            self._handle = None


def enqueue(
    name: str,
    payload: dict[str, Any],
    *,
    queue_dir: Path | None = None,
    dlq_dir: Path | None = None,
) -> None:
    """단일 작업을 큐 끝에 atomic append. flock으로 동시성 보호."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    paths = QueuePaths.for_name(name, queue_dir=queue_dir, dlq_dir=dlq_dir)
    enriched = {**payload, "enqueued_at": payload.get("enqueued_at") or utc_now()}
    line = json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n"
    with _FileLock(paths.lock):
        with paths.queue.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def drain(
    name: str,
    *,
    queue_dir: Path | None = None,
    dlq_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """큐 전체를 한 번에 비우고 list로 반환. flock 보호.

    소비 도중 실패하면 호출자가 dead_letter()로 다시 보내야 한다.
    드레인 후 큐 파일은 0바이트로 truncate (파일 자체는 보존).
    """
    paths = QueuePaths.for_name(name, queue_dir=queue_dir, dlq_dir=dlq_dir)
    items: list[dict[str, Any]] = []
    with _FileLock(paths.lock):
        if not paths.queue.exists():
            return items
        with paths.queue.open("r+", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    items.append(item)
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    return items


def peek(
    name: str,
    *,
    queue_dir: Path | None = None,
    dlq_dir: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """큐를 비우지 않고 읽기 전용 스냅샷."""
    paths = QueuePaths.for_name(name, queue_dir=queue_dir, dlq_dir=dlq_dir)
    if not paths.queue.exists():
        return
    with _FileLock(paths.lock):
        snapshot = paths.queue.read_text(encoding="utf-8")
    for line in snapshot.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            yield item


def dead_letter(
    name: str,
    payload: dict[str, Any],
    *,
    reason: str,
    queue_dir: Path | None = None,
    dlq_dir: Path | None = None,
) -> None:
    """작업 처리 실패 시 dead-letter 큐로 이동."""
    paths = QueuePaths.for_name(name, queue_dir=queue_dir, dlq_dir=dlq_dir)
    enriched = {
        "original": payload,
        "reason": reason,
        "moved_at": utc_now(),
    }
    line = json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n"
    dlq_lock = paths.dead_letter.with_suffix(".lock")
    with _FileLock(dlq_lock):
        with paths.dead_letter.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def length(
    name: str,
    *,
    queue_dir: Path | None = None,
    dlq_dir: Path | None = None,
) -> int:
    paths = QueuePaths.for_name(name, queue_dir=queue_dir, dlq_dir=dlq_dir)
    if not paths.queue.exists():
        return 0
    with _FileLock(paths.lock):
        return sum(1 for line in paths.queue.read_text(encoding="utf-8").splitlines() if line.strip())


def main(argv: list[str] | None = None) -> int:
    """CLI: enqueue/drain/peek/length/dlq subcommand."""
    import argparse

    parser = argparse.ArgumentParser(description="Synapse queue CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_enq = sub.add_parser("enqueue", help="JSON payload를 stdin 또는 --json 으로 입력")
    p_enq.add_argument("name")
    p_enq.add_argument("--json", help="JSON payload (omit → read from stdin)")

    p_drain = sub.add_parser("drain", help="큐를 비우고 stdout에 JSONL로 출력")
    p_drain.add_argument("name")

    p_peek = sub.add_parser("peek", help="큐를 비우지 않고 stdout에 JSONL로 출력")
    p_peek.add_argument("name")

    p_len = sub.add_parser("length", help="큐 길이")
    p_len.add_argument("name")

    p_dlq = sub.add_parser("dead-letter", help="payload를 DLQ로 직접 이동")
    p_dlq.add_argument("name")
    p_dlq.add_argument("--reason", required=True)
    p_dlq.add_argument("--json", help="JSON payload (omit → stdin)")

    args = parser.parse_args(argv)

    import sys

    if args.cmd == "enqueue":
        raw = args.json if args.json else sys.stdin.read()
        payload = json.loads(raw)
        enqueue(args.name, payload)
        return 0

    if args.cmd == "drain":
        for item in drain(args.name):
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd == "peek":
        for item in peek(args.name):
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd == "length":
        print(length(args.name))
        return 0

    if args.cmd == "dead-letter":
        raw = args.json if args.json else sys.stdin.read()
        payload = json.loads(raw)
        dead_letter(args.name, payload, reason=args.reason)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
