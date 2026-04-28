#!/usr/bin/env python3
"""
Synapse pipeline checkpoint store.

Author: jimmy
Date: 2026-04-28

각 collector(claude/codex)별로 마지막 처리 위치를 기록한다. 동일 입력의 반복
처리를 막기 위해 content_hash 기반 dedup도 함께.

Layout:
  ~/.synapse/private/checkpoints/<source>.json

Schema (Checkpoint-v1):
  {
    "schema_version": "Checkpoint-v1",
    "source": "claude" | "codex",
    "last_run_at": "2026-04-28T01:23:45Z",
    "last_processed_path": "/path/to/last.jsonl",
    "last_offset": 12345,                       # byte offset (incremental tail)
    "content_hashes_seen": ["sha256...", ...],  # 직전 N개 (기본 256)
  }

Atomic write: tmp+rename. flock 잠금.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from collections import deque
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path.home() / ".synapse" / "private"
DEFAULT_DIR = PRIVATE_ROOT / "checkpoints"
HASH_HISTORY_LIMIT = 256
ALLOWED_SOURCES = {"claude", "codex"}


class CheckpointError(Exception):
    """Raised when checkpoint validation fails."""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _path_for(source: str, base_dir: Path | None = None) -> Path:
    if source not in ALLOWED_SOURCES:
        raise CheckpointError(f"unknown source: {source}")
    base = (base_dir or DEFAULT_DIR).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{source}.json"


def _empty(source: str) -> dict[str, Any]:
    return {
        "schema_version": "Checkpoint-v1",
        "source": source,
        "last_run_at": None,
        "last_processed_path": None,
        "last_offset": 0,
        "content_hashes_seen": [],
    }


def _read_unlocked(path: Path, source: str) -> dict[str, Any]:
    """락 없이 파일 read + schema validation. lock holder 내부에서만 사용."""
    if not path.exists():
        return _empty(source)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CheckpointError(f"checkpoint not an object: {path}")
    if data.get("schema_version") != "Checkpoint-v1":
        raise CheckpointError(f"checkpoint schema mismatch: {path}")
    if data.get("source") != source:
        raise CheckpointError(f"checkpoint source mismatch: {path}")
    if not isinstance(data.get("content_hashes_seen"), list):
        raise CheckpointError(f"checkpoint content_hashes_seen invalid: {path}")
    return data


def load(source: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    path = _path_for(source, base_dir)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "a+") as lh:
        fcntl.flock(lh.fileno(), fcntl.LOCK_SH)
        try:
            return _read_unlocked(path, source)
        finally:
            fcntl.flock(lh.fileno(), fcntl.LOCK_UN)


def save(
    source: str,
    *,
    last_processed_path: str | None = None,
    last_offset: int | None = None,
    add_content_hash: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """체크포인트 갱신. atomic tmp+rename + flock.

    flock 재진입 데드락 방지: 단일 락 안에서 read → mutate → write 모두 처리.
    """
    if last_offset is not None and last_offset < 0:
        raise CheckpointError("last_offset must be non-negative")

    path = _path_for(source, base_dir)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "a+") as lh:
        fcntl.flock(lh.fileno(), fcntl.LOCK_EX)
        try:
            try:
                current = _read_unlocked(path, source)
            except CheckpointError:
                current = _empty(source)

            if last_processed_path is not None:
                current["last_processed_path"] = last_processed_path
            if last_offset is not None:
                current["last_offset"] = last_offset
            if add_content_hash is not None:
                history = deque(current.get("content_hashes_seen", []), maxlen=HASH_HISTORY_LIMIT)
                if add_content_hash not in history:
                    history.append(add_content_hash)
                current["content_hashes_seen"] = list(history)

            current["last_run_at"] = utc_now()

            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            fcntl.flock(lh.fileno(), fcntl.LOCK_UN)
    return current


def has_seen(source: str, content_hash: str, *, base_dir: Path | None = None) -> bool:
    """이미 처리한 content_hash 인지."""
    try:
        data = load(source, base_dir=base_dir)
    except CheckpointError:
        return False
    return content_hash in data.get("content_hashes_seen", [])


def reset(source: str, *, base_dir: Path | None = None) -> None:
    """체크포인트를 비운다 (백필 등 명시 사용)."""
    path = _path_for(source, base_dir)
    if path.exists():
        path.unlink()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Synapse checkpoint CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show")
    p_show.add_argument("source", choices=sorted(ALLOWED_SOURCES))

    p_save = sub.add_parser("save")
    p_save.add_argument("source", choices=sorted(ALLOWED_SOURCES))
    p_save.add_argument("--last-processed-path")
    p_save.add_argument("--last-offset", type=int)
    p_save.add_argument("--add-content-hash")

    p_seen = sub.add_parser("has-seen")
    p_seen.add_argument("source", choices=sorted(ALLOWED_SOURCES))
    p_seen.add_argument("content_hash")

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("source", choices=sorted(ALLOWED_SOURCES))

    args = parser.parse_args(argv)

    if args.cmd == "show":
        print(json.dumps(load(args.source), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.cmd == "save":
        result = save(
            args.source,
            last_processed_path=args.last_processed_path,
            last_offset=args.last_offset,
            add_content_hash=args.add_content_hash,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.cmd == "has-seen":
        print("yes" if has_seen(args.source, args.content_hash) else "no")
        return 0

    if args.cmd == "reset":
        reset(args.source)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
