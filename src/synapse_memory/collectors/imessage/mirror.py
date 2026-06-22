"""iMessage → L0 mirror.

소스: ``~/Library/Messages/chat.db`` (SQLite)
대상: ``~/.synapse/private/raw/imessage/chat.db``

Cursor 패턴과 동일 — ``sqlite3.Connection.backup`` 으로 read-consistent
snapshot. Full Disk Access 권한 부재 시 ``PermissionError`` 가 errors 에 누적
(빈 통계 반환 — daily 파이프라인 중단 안 됨).

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.collectors._filestate import (
    FileState,
    file_sha256 as _file_sha256,
    load_states as _load_states,
    save_states_atomic as _save_states_atomic,
)
from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_MESSAGES_HOME = Path.home() / "Library" / "Messages"
ENV_DISABLE = "SYNAPSE_IMESSAGE_DISABLE"
SUBPATH = Path("raw") / "imessage"
META_DIR = ".meta"
STATES_FILE = "states.json"

# 본 컬렉터는 chat.db 만 처리. attachment/sticker 등은 후속 PR.
INCLUDED_NAMES: frozenset[str] = frozenset({"chat.db"})

__all__ = [
    "DEFAULT_MESSAGES_HOME",
    "ENV_DISABLE",
    "SUBPATH",
    "CollectStats",
    "collect_imessage",
]


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


def collect_imessage(
    *,
    messages_home: Path | None = None,
    dst_root: Path | None = None,
    disable_env: str | None = None,
) -> CollectStats:
    """iMessage chat.db 1회 수집 (incremental).

    Args:
        messages_home: ``~/Library/Messages`` (기본).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/imessage``).
        disable_env: ``SYNAPSE_IMESSAGE_DISABLE`` env 값 override (테스트용).

    Returns:
        CollectStats. ``DISABLE`` env truthy 시 빈 통계 (opt-out).
        ``messages_home`` 미존재 또는 권한 없을 시 errors 에 기록 후 반환.
    """
    disable_val = (
        disable_env if disable_env is not None else os.environ.get(ENV_DISABLE)
    )
    if disable_val and disable_val.lower() not in ("", "0", "false", "no"):
        return CollectStats()

    home = (messages_home or DEFAULT_MESSAGES_HOME).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not home.is_dir():
        stats.errors.append((home, f"Messages home 없음: {home}"))
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    for name in sorted(INCLUDED_NAMES):
        src = home / name
        if not src.is_file():
            continue
        stats.files_scanned += 1
        rel_key = name
        try:
            st = src.stat()
            mtime, size = st.st_mtime, st.st_size

            prev_state = prev.get(rel_key)
            if prev_state and prev_state.mtime == mtime and prev_state.size == size:
                new_states[rel_key] = prev_state
                stats.files_unchanged += 1
                continue

            dst_file = dst / name
            _sqlite_backup(src, dst_file)
            sha = _file_sha256(dst_file)

            if prev_state and prev_state.sha256 == sha:
                new_states[rel_key] = FileState(
                    rel_path=rel_key, mtime=mtime, size=size, sha256=sha
                )
                stats.files_unchanged += 1
                continue

            stats.files_mirrored += 1
            stats.bytes_added += dst_file.stat().st_size
            new_states[rel_key] = FileState(
                rel_path=rel_key, mtime=mtime, size=size, sha256=sha
            )
        except (OSError, sqlite3.Error) as exc:
            stats.errors.append((src, str(exc)))

    _save_states_atomic(meta_path, new_states)
    return stats
