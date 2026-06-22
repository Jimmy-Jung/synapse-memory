"""Apple Health → L0 mirror.

소스: ``SYNAPSE_HEALTH_DROP`` (기본 ``~/Downloads``) 안의 ``export*.zip``.
대상: ``~/.synapse/private/raw/apple-health/<filename>``

obsidian/calendar 와 동일한 mtime+size+sha256 변경 감지. zip 안 내용은 본 단계
에서 풀지 않음 (후속 unzip + XML 파싱 단계 책임).

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

ENV_DROP_DIR = "SYNAPSE_HEALTH_DROP"
DEFAULT_DROP_DIR = Path.home() / "Downloads"
SUBPATH = Path("raw") / "apple-health"
META_DIR = ".meta"
STATES_FILE = "states.json"

GLOB_PATTERN = "export*.zip"

__all__ = [
    "DEFAULT_DROP_DIR",
    "ENV_DROP_DIR",
    "SUBPATH",
    "CollectStats",
    "collect_apple_health",
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


def collect_apple_health(
    *,
    drop_dir: Path | None = None,
    drop_dir_env: str | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Apple Health export 1회 수집 (incremental).

    Args:
        drop_dir: drop-in 디렉토리 (테스트용 override).
        drop_dir_env: ``SYNAPSE_HEALTH_DROP`` env 값 override (테스트용).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/apple-health``).

    Resolution:
        1. ``drop_dir`` 인자
        2. ``drop_dir_env`` 인자 또는 ``SYNAPSE_HEALTH_DROP`` env
        3. ``DEFAULT_DROP_DIR``

    Returns:
        CollectStats — 처리 통계. drop_dir 미존재 시 errors 없이 빈 통계.
    """
    if drop_dir is not None:
        src_dir = drop_dir
    else:
        env_val = (
            drop_dir_env
            if drop_dir_env is not None
            else os.environ.get(ENV_DROP_DIR)
        )
        src_dir = Path(env_val).expanduser() if env_val else DEFAULT_DROP_DIR

    src_dir = src_dir.expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not src_dir.is_dir():
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    for src in sorted(src_dir.glob(GLOB_PATTERN)):
        if not src.is_file():
            continue
        stats.files_scanned += 1
        rel_key = src.name
        try:
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

            dst_file = dst / src.name
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
