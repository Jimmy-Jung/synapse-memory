#!/usr/bin/env python3
"""
Warn and archive old normalized SessionRecord files when storage grows.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import shutil
from pathlib import Path
from typing import Any


AI_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NORMALIZED_DIR = Path.home() / ".synapse" / "private" / "normalized"
DEFAULT_REVIEW_PATH = AI_ROOT / "MemoryReview.md"
DEFAULT_THRESHOLD_BYTES = 1_000_000_000
DEFAULT_OLDER_THAN_DAYS = 90


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def old_json_files(path: Path, *, older_than_days: int, now: dt.datetime | None = None) -> list[Path]:
    if not path.exists():
        return []
    now_value = now or dt.datetime.now(dt.UTC)
    cutoff = now_value - dt.timedelta(days=older_than_days)
    files: list[Path] = []
    for item in path.rglob("*.json"):
        if not item.is_file():
            continue
        mtime = dt.datetime.fromtimestamp(item.stat().st_mtime, tz=dt.UTC)
        if mtime < cutoff:
            files.append(item)
    return sorted(files)


def gzip_file(path: Path) -> Path:
    target = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as source, gzip.open(target, "wb") as dest:
        shutil.copyfileobj(source, dest)
    path.unlink()
    return target


def append_warning(review_path: Path, line: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    base = review_path.read_text(encoding="utf-8") if review_path.exists() else "# Memory Review\n\n"
    tmp = review_path.with_name(f".{review_path.name}.tmp.{os.getpid()}")
    tmp.write_text(base.rstrip() + "\n" + line + "\n", encoding="utf-8")
    os.replace(tmp, review_path)


def archive_normalized(
    *,
    normalized_dir: Path = DEFAULT_NORMALIZED_DIR,
    review_path: Path = DEFAULT_REVIEW_PATH,
    threshold_bytes: int = DEFAULT_THRESHOLD_BYTES,
    older_than_days: int = DEFAULT_OLDER_THAN_DAYS,
    dry_run: bool = False,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    size = directory_size(normalized_dir)
    candidates = old_json_files(normalized_dir, older_than_days=older_than_days, now=now) if size > threshold_bytes else []
    archived: list[str] = []
    for path in candidates:
        if dry_run:
            archived.append(str(path.with_suffix(path.suffix + ".gz")))
        else:
            archived.append(str(gzip_file(path)))
    warning = None
    if size > threshold_bytes:
        warning = (
            f"- {(now or dt.datetime.now(dt.UTC)).date().isoformat()}: normalized store size={size} "
            f"threshold={threshold_bytes} archived={len(archived)} dry_run={dry_run}"
        )
        append_warning(review_path, warning, dry_run=dry_run)
    return {
        "dry_run": dry_run,
        "size_bytes": size,
        "threshold_bytes": threshold_bytes,
        "archive_candidates": len(candidates),
        "archived": archived,
        "warning": warning,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive old normalized SessionRecord files")
    parser.add_argument("--threshold-bytes", type=int, default=DEFAULT_THRESHOLD_BYTES)
    parser.add_argument("--older-than-days", type=int, default=DEFAULT_OLDER_THAN_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = archive_normalized(
        threshold_bytes=args.threshold_bytes,
        older_than_days=args.older_than_days,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
