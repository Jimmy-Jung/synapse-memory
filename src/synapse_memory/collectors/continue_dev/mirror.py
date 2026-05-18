"""Continue.dev → L0 mirror.

소스:
    ``~/.continue/sessions/*.json``  — 세션 JSON
    ``~/.continue/dev_data/*.jsonl`` — telemetry JSONL

대상: ``~/.synapse/private/raw/continue/`` 아래 동일 상대 경로.

obsidian mirror 와 동일한 mtime+size+sha256 3-tier 변경 감지. JSON 은
atomic save 라 단순 byte copy 안전.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_CONTINUE_HOME = Path.home() / ".continue"
SUBPATH = Path("raw") / "continue"
META_DIR = ".meta"
STATES_FILE = "states.json"

INCLUDED_EXTS: tuple[str, ...] = (".json", ".jsonl")
EXCLUDED_TOP_FILES: frozenset[str] = frozenset(
    {"index.json", "config.json", ".lock"}
)


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


def _enumerate(continue_home: Path) -> list[Path]:
    """수집 대상 — sessions/ 와 dev_data/ 안의 JSON / JSONL.

    제외: ~/.continue/ 최상위의 index.json / config.json (메타·설정).
    """
    targets: list[Path] = []
    for sub in ("sessions", "dev_data"):
        root = continue_home / sub
        if not root.is_dir():
            continue
        for ext in INCLUDED_EXTS:
            for p in sorted(root.rglob(f"*{ext}")):
                if p.is_file() and p.name not in EXCLUDED_TOP_FILES:
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


def collect_continue(
    *,
    continue_home: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Continue.dev 데이터 1회 수집 (incremental).

    Args:
        continue_home: ``~/.continue`` (기본). 미존재 시 errors 없이 빈 통계 반환
            (Continue.dev 미설치 사용자 — 정상 상태).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/continue``).

    Returns:
        CollectStats — 처리 통계.
    """
    home = (continue_home or DEFAULT_CONTINUE_HOME).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not home.is_dir():
        return stats  # Continue.dev 미설치 — 정상

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
