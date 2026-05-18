"""브라우저 history → L0 mirror.

Chrome/Safari/Arc 등 macOS 표준 위치의 History SQLite 를 ``sqlite3.backup`` 으로
read-consistent snapshot. 브라우저 실행 중에도 안전 (page-level lock 협상).

브라우저별 기본 경로:
    Chrome  — ~/Library/Application Support/Google/Chrome/Default/History
    Safari  — ~/Library/Safari/History.db
    Arc     — ~/Library/Application Support/Arc/User Data/Default/History
    (그 외 브라우저는 ``browsers`` 인자로 BrowserSource 주입)

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

SUBPATH = Path("raw") / "browser-history"
META_DIR = ".meta"
STATES_FILE = "states.json"


@dataclass(frozen=True)
class BrowserSource:
    name: str
    db_path: Path
    dst_filename: str = "History"


DEFAULT_BROWSERS: tuple[BrowserSource, ...] = (
    BrowserSource(
        name="chrome",
        db_path=(
            Path.home()
            / "Library"
            / "Application Support"
            / "Google"
            / "Chrome"
            / "Default"
            / "History"
        ),
    ),
    BrowserSource(
        name="safari",
        db_path=Path.home() / "Library" / "Safari" / "History.db",
    ),
    BrowserSource(
        name="arc",
        db_path=(
            Path.home()
            / "Library"
            / "Application Support"
            / "Arc"
            / "User Data"
            / "Default"
            / "History"
        ),
    ),
)

__all__ = [
    "DEFAULT_BROWSERS",
    "SUBPATH",
    "BrowserSource",
    "CollectStats",
    "collect_browser_history",
]


@dataclass
class FileState:
    rel_path: str
    mtime: float
    size: int
    sha256: str


@dataclass
class CollectStats:
    browsers_scanned: int = 0
    browsers_mirrored: int = 0
    browsers_unchanged: int = 0
    bytes_added: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned={self.browsers_scanned} "
            f"mirrored={self.browsers_mirrored} "
            f"unchanged={self.browsers_unchanged} bytes+={self.bytes_added} "
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


def collect_browser_history(
    *,
    browsers: tuple[BrowserSource, ...] | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """브라우저 history 1회 수집 (incremental, per-browser).

    Args:
        browsers: 처리할 BrowserSource 리스트 (기본: macOS 표준 Chrome/Safari/Arc).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/browser-history``).

    Returns:
        CollectStats — 처리 통계. 각 브라우저별로 미존재 시 silent skip,
        backup 실패는 errors 에 누적.
    """
    browsers = browsers if browsers is not None else DEFAULT_BROWSERS
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    for browser in browsers:
        src = browser.db_path.expanduser().resolve()
        if not src.is_file():
            continue
        stats.browsers_scanned += 1
        rel_key = f"{browser.name}/{browser.dst_filename}"
        try:
            st = src.stat()
            mtime, size = st.st_mtime, st.st_size

            prev_state = prev.get(rel_key)
            if prev_state and prev_state.mtime == mtime and prev_state.size == size:
                new_states[rel_key] = prev_state
                stats.browsers_unchanged += 1
                continue

            dst_file = dst / browser.name / browser.dst_filename
            _sqlite_backup(src, dst_file)
            sha = _file_sha256(dst_file)

            if prev_state and prev_state.sha256 == sha:
                new_states[rel_key] = FileState(
                    rel_path=rel_key, mtime=mtime, size=size, sha256=sha
                )
                stats.browsers_unchanged += 1
                continue

            stats.browsers_mirrored += 1
            stats.bytes_added += dst_file.stat().st_size
            new_states[rel_key] = FileState(
                rel_path=rel_key, mtime=mtime, size=size, sha256=sha
            )
        except (OSError, sqlite3.Error) as exc:
            stats.errors.append((browser.name, str(exc)))

    _save_states_atomic(meta_path, new_states)
    return stats
