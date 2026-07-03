"""SQLite file → L0 mirror 공통 헬퍼.

여러 컬렉터(day_one 등)가
모두 같은 패턴 — ``sqlite3.Connection.backup`` 으로 read-consistent snapshot 을
뜨고, mtime+sha256 으로 변경 감지 — 을 쓴다. 본 모듈에 통합.

``cursor.mirror`` 는 본 헬퍼 도입 전에 작성됐고 PR #21 에서 검증됐기 때문에
본 PR 에선 그대로 두고, 후속 PR 에서 따라 통일한다 (risk 회피).

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.collectors._filestate import (
    FileState,
    file_sha256,
    load_states,
    save_states_atomic,
)
from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_SQLITE_EXTS: tuple[str, ...] = (".sqlite", ".db", ".vscdb", ".storedata")
META_DIR = ".meta"
STATES_FILE = "states.json"

# 변경 감지 state 헬퍼는 _filestate 에서 공용화. 하위 호환 위해 re-export.
__all__ = [
    "FileState",
    "file_sha256",
    "load_states",
    "save_states_atomic",
]


@dataclass
class SqliteCollectStats:
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


def _is_sidecar(name: str) -> bool:
    """SQLite WAL/SHM/journal 동반 파일 여부."""
    return name.endswith(("-wal", "-shm", "-journal"))


def enumerate_sqlite(
    home: Path,
    *,
    sqlite_exts: Iterable[str] = DEFAULT_SQLITE_EXTS,
    excluded_top_dirs: Iterable[str] = (),
    extra_filter: Callable[[Path], bool] | None = None,
) -> list[Path]:
    """``home`` 아래 SQLite 파일 enumeration. WAL/SHM/journal 제외.

    Args:
        home: 검색 루트.
        sqlite_exts: 허용 확장자.
        excluded_top_dirs: ``home`` 직계 자식 디렉토리 이름 (logs, cache 등).
        extra_filter: 추가 필터 (True 반환 시 포함). 절대 경로 받음.
    """
    excluded = frozenset(excluded_top_dirs)
    targets: list[Path] = []
    for ext in sqlite_exts:
        for p in sorted(home.rglob(f"*{ext}")):
            if not p.is_file():
                continue
            if _is_sidecar(p.name):
                continue
            rel = p.relative_to(home)
            top = rel.parts[0] if rel.parts else ""
            if top in excluded:
                continue
            if extra_filter is not None and not extra_filter(p):
                continue
            targets.append(p)
    return targets


def sqlite_backup(src: Path, dst: Path) -> None:
    """SQLite read-consistent backup. WAL/lock 안전.

    Raises:
        sqlite3.Error: backup 실패 (corrupt source, permission 등).
        OSError: 파일 시스템 에러.
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


def mirror_sqlite_tree(
    *,
    home: Path,
    dst_root: Path,
    sqlite_exts: Iterable[str] = DEFAULT_SQLITE_EXTS,
    excluded_top_dirs: Iterable[str] = (),
    extra_filter: Callable[[Path], bool] | None = None,
) -> SqliteCollectStats:
    """``home`` 아래 SQLite 트리 → ``dst_root`` mirror (incremental).

    공통 패턴:
    1. enumerate SQLite (WAL/SHM 제외, excluded_top_dirs 제외)
    2. mtime+size 변경 없으면 skip
    3. sqlite_backup 후 sha256 비교 — backup 결과가 같으면 unchanged 처리
    4. states JSON 갱신
    """
    home = home.expanduser().resolve()
    dst_root = dst_root.expanduser().resolve()
    stats = SqliteCollectStats()

    if not home.is_dir():
        stats.errors.append((home, f"home 없음: {home}"))
        return stats

    if dst_root.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst_root)
    ensure_secure_dir(dst_root / META_DIR)

    meta_path = dst_root / META_DIR / STATES_FILE
    prev = load_states(meta_path)
    new_states: dict[str, FileState] = {}

    targets = enumerate_sqlite(
        home,
        sqlite_exts=sqlite_exts,
        excluded_top_dirs=excluded_top_dirs,
        extra_filter=extra_filter,
    )

    for src in targets:
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

            dst_file = dst_root / rel
            sqlite_backup(src, dst_file)
            sha = file_sha256(dst_file)

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

    save_states_atomic(meta_path, new_states)
    return stats
