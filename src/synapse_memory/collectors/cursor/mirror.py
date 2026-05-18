"""Cursor IDE → L0 mirror.

소스 (macOS): ``~/Library/Application Support/Cursor/User/{workspaceStorage,
globalStorage}/.../state.vscdb`` 등 SQLite 파일.

핵심 차이 (obsidian mirror 대비)
--------------------------------
- 단위가 SQLite DB 파일 — :func:`sqlite3.Connection.backup` 으로 atomic snapshot.
- WAL/lock 가능 → ``sqlite3`` URI ``mode=ro`` 로 read-only open.
- Cursor 가 동시 쓰는 중이면 backup API 가 자동으로 page-level lock 협상.
- 단순 file copy 사용 안 함 (truncated/corrupt snapshot 위험).
- 변경 감지: mtime + size → 같으면 skip. 다르면 backup → sha256 비교 →
  진짜 변경 시만 dst 갱신.

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

DEFAULT_CURSOR_HOME = (
    Path.home() / "Library" / "Application Support" / "Cursor" / "User"
)
SUBPATH = Path("raw") / "cursor"
META_DIR = ".meta"
STATES_FILE = "states.json"

SQLITE_EXTS: tuple[str, ...] = (".vscdb", ".sqlite", ".db")
EXCLUDED_TOP_DIRS: frozenset[str] = frozenset({"logs", "logs.old", "History"})


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


def _enumerate_sqlite(cursor_home: Path) -> list[Path]:
    """수집 대상 SQLite 파일 목록.

    포함:
        ``<home>/workspaceStorage/<hash>/state.vscdb``
        ``<home>/globalStorage/state.vscdb``

    제외:
        ``*.vscdb-wal`` / ``*.vscdb-shm`` (backup API 가 알아서 통합)
        ``logs/``, ``History/`` (대용량 캐시)
    """
    targets: list[Path] = []
    for ext in SQLITE_EXTS:
        for p in sorted(cursor_home.rglob(f"*{ext}")):
            if not p.is_file():
                continue
            name = p.name
            if (
                name.endswith("-wal")
                or name.endswith("-shm")
                or name.endswith("-journal")
            ):
                continue
            rel = p.relative_to(cursor_home)
            top = rel.parts[0] if rel.parts else ""
            if top in EXCLUDED_TOP_DIRS:
                continue
            targets.append(p)
    return targets


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
    """SQLite read-consistent backup. WAL/lock 안전.

    Raises:
        sqlite3.Error: backup 실패 (corrupt source, permission 등).
    """
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


def collect_cursor(
    *,
    cursor_home: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Cursor IDE 데이터 1회 수집 (incremental).

    Args:
        cursor_home: Cursor User 디렉토리 (기본: macOS 표준 경로).
            미존재 시 errors 에 기록 후 반환.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/cursor``).

    Returns:
        CollectStats — 처리 통계.
    """
    home = (cursor_home or DEFAULT_CURSOR_HOME).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not home.is_dir():
        stats.errors.append((home, f"Cursor home 없음: {home}"))
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()

    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    for src in _enumerate_sqlite(home):
        stats.files_scanned += 1
        try:
            rel = src.relative_to(home)
            rel_key = rel.as_posix()
            st = src.stat()
            mtime, size = st.st_mtime, st.st_size

            prev_state = prev.get(rel_key)
            if prev_state and prev_state.mtime == mtime and prev_state.size == size:
                new_states[rel_key] = prev_state
                stats.files_unchanged += 1
                continue

            dst_file = dst / rel
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
