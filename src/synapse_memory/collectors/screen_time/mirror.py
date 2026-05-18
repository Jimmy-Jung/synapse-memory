"""Screen Time → L0 mirror.

소스: ``~/Library/Application Support/Knowledge/knowledgeC.db``
대상: ``~/.synapse/private/raw/screen-time/knowledgeC.db``

cursor/browser_history 와 동일한 sqlite3.backup + mtime/sha256 패턴. 단일
파일이라 단순.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_KNOWLEDGEC_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Knowledge"
    / "knowledgeC.db"
)
SUBPATH = Path("raw") / "screen-time"
META_DIR = ".meta"
STATES_FILE = "states.json"
DST_FILENAME = "knowledgeC.db"

__all__ = [
    "DEFAULT_KNOWLEDGEC_DB",
    "SUBPATH",
    "CollectStats",
    "collect_screen_time",
]


@dataclass
class FileState:
    rel_path: str
    mtime: float
    size: int
    sha256: str


@dataclass
class CollectStats:
    files_scanned: int = 0
    files_mirrored: int = 0
    files_unchanged: int = 0
    bytes_added: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned={self.files_scanned} mirrored={self.files_mirrored} "
            f"unchanged={self.files_unchanged} bytes+={self.bytes_added} "
            f"errors={len(self.errors)}"
        )


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_states(meta_path: Path) -> dict[str, FileState]:
    if not meta_path.exists():
        return {}
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, FileState] = {}
    for item in raw:
        try:
            s = FileState(
                rel_path=str(item["rel_path"]),
                mtime=float(item["mtime"]),
                size=int(item["size"]),
                sha256=str(item["sha256"]),
            )
            out[s.rel_path] = s
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _save_states_atomic(meta_path: Path, states: dict[str, FileState]) -> None:
    ensure_secure_dir(meta_path.parent)
    payload = json.dumps(
        [asdict(s) for s in states.values()],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(tmp, L0_FILE_MODE)
    os.replace(tmp, meta_path)


def _sqlite_backup(src: Path, dst: Path) -> None:
    src_uri = f"file:{src}?mode=ro"
    ensure_secure_dir(dst.parent)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    src_conn = sqlite3.connect(src_uri, uri=True)
    try:
        dst_conn = sqlite3.connect(str(tmp))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    with contextlib.suppress(OSError):
        os.chmod(tmp, L0_FILE_MODE)
    os.replace(tmp, dst)


def collect_screen_time(
    *,
    db_path: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Screen Time / knowledgeC.db 1회 수집 (incremental).

    Args:
        db_path: knowledgeC.db (기본).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/screen-time``).

    Returns:
        CollectStats — 처리 통계. DB 미존재 시 errors 없이 빈 통계.
        backup 실패는 errors 누적.
    """
    src = (db_path or DEFAULT_KNOWLEDGEC_DB).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not src.is_file():
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    stats.files_scanned += 1
    rel_key = DST_FILENAME
    try:
        st = src.stat()
        mtime, size = st.st_mtime, st.st_size

        prev_state = prev.get(rel_key)
        if prev_state and prev_state.mtime == mtime and prev_state.size == size:
            new_states[rel_key] = prev_state
            stats.files_unchanged += 1
        else:
            dst_file = dst / DST_FILENAME
            _sqlite_backup(src, dst_file)
            sha = _file_sha256(dst_file)

            if prev_state and prev_state.sha256 == sha:
                new_states[rel_key] = FileState(
                    rel_path=rel_key, mtime=mtime, size=size, sha256=sha
                )
                stats.files_unchanged += 1
            else:
                stats.files_mirrored += 1
                stats.bytes_added += dst_file.stat().st_size
                new_states[rel_key] = FileState(
                    rel_path=rel_key, mtime=mtime, size=size, sha256=sha
                )
    except (OSError, sqlite3.Error) as exc:
        stats.errors.append((src, str(exc)))

    _save_states_atomic(meta_path, new_states)
    return stats
