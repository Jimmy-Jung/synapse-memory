"""VS Code Local History → L0 mirror.

소스: ``~/Library/Application Support/Code/User/History/`` 아래 모든 파일.
대상: ``~/.synapse/private/raw/vscode-local-history/`` 아래 동일 구조.

obsidian/continue_dev 와 동일한 mtime+size+sha256 3-tier 변경 감지 패턴이지만
VS Code 가 binary 파일도 snapshot 할 수 있어 ``rb`` 모드 copy.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import os
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

DEFAULT_VSCODE_HISTORY = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Code"
    / "User"
    / "History"
)
SUBPATH = Path("raw") / "vscode-local-history"
META_DIR = ".meta"
STATES_FILE = "states.json"

__all__ = [
    "DEFAULT_VSCODE_HISTORY",
    "SUBPATH",
    "CollectStats",
    "collect_vscode_local_history",
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


def _enumerate(history_home: Path) -> list[Path]:
    """``<home>/<dir-hash>/*`` 모든 파일. symlink 제외."""
    targets: list[Path] = []
    for p in sorted(history_home.rglob("*")):
        if p.is_file() and not p.is_symlink():
            targets.append(p)
    return targets


def collect_vscode_local_history(
    *,
    history_home: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """VS Code Local History 1회 수집 (incremental).

    Args:
        history_home: ``~/Library/.../Code/User/History`` (기본).
            미존재 시 errors 없이 빈 통계 (VS Code 미설치 또는 history 사용
            안 함 — 정상).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/vscode-local-history``).

    Returns:
        CollectStats — 처리 통계.
    """
    home = (history_home or DEFAULT_VSCODE_HISTORY).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not home.is_dir():
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    for src in _enumerate(home):
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

            sha = _file_sha256(src)
            if prev_state and prev_state.sha256 == sha:
                new_states[rel_key] = FileState(
                    rel_path=rel_key, mtime=mtime, size=size, sha256=sha
                )
                stats.files_unchanged += 1
                continue

            dst_file = dst / rel
            ensure_secure_dir(dst_file.parent)
            dst_file.write_bytes(src.read_bytes())
            with contextlib.suppress(OSError):
                os.chmod(dst_file, L0_FILE_MODE)

            stats.files_mirrored += 1
            stats.bytes_added += size
            new_states[rel_key] = FileState(
                rel_path=rel_key, mtime=mtime, size=size, sha256=sha
            )
        except OSError as exc:
            stats.errors.append((src, str(exc)))

    _save_states_atomic(meta_path, new_states)
    return stats
