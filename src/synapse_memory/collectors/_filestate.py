"""파일 변경 감지용 공통 state 헬퍼.

파일 기반 컬렉터가 쓰는 패턴 —
``mtime``+``size``+``sha256`` prefix 로 파일 변경을 감지하고 ``states.json`` 에
원자적으로 저장 — 을 쓴다. 본 모듈에 통합한다.

저자: Synapse Memory Maintainers
작성일: 2026-06-22
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from synapse_memory.storage.l0 import L0_FILE_MODE, ensure_secure_dir


@dataclass
class FileState:
    """이전 mirror 시점의 파일 메타. 변경 감지용."""

    rel_path: str
    mtime: float
    size: int
    sha256: str


def file_sha256(path: Path) -> str:
    """파일 sha256 — 16자 prefix만 (전체는 과도, 충돌 거의 없음)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_states(meta_path: Path) -> dict[str, FileState]:
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


def save_states_atomic(meta_path: Path, states: dict[str, FileState]) -> None:
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
