"""Apple Notes → L0 mirror.

소스: ``~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite``
      (+ WAL/SHM 동반 파일)
대상: ``~/.synapse/private/raw/apple-notes/`` 아래 동일 파일명.

공통 ``_sqlite_mirror.mirror_sqlite_tree`` 헬퍼 사용. NoteStore 만 단일 파일이라
sqlite_exts 를 ``.sqlite`` 로 한정.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.collectors._sqlite_mirror import (
    SqliteCollectStats as CollectStats,
)
from synapse_memory.collectors._sqlite_mirror import (
    mirror_sqlite_tree,
)
from synapse_memory.storage.l0 import l0_root

DEFAULT_NOTES_HOME = (
    Path.home() / "Library" / "Group Containers" / "group.com.apple.notes"
)
SUBPATH = Path("raw") / "apple-notes"

__all__ = [
    "DEFAULT_NOTES_HOME",
    "SUBPATH",
    "CollectStats",
    "collect_apple_notes",
]


def collect_apple_notes(
    *,
    notes_home: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Apple Notes 데이터 1회 수집 (incremental).

    Args:
        notes_home: Group Containers/group.com.apple.notes (기본).
            미존재 시 errors 에 기록 후 빈 통계 반환 (Notes 미사용 또는 권한
            부족 — Full Disk Access 부재 시 ``OSError`` 가 errors 에 쌓임).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/apple-notes``).

    Returns:
        CollectStats — 처리 통계.
    """
    home = notes_home or DEFAULT_NOTES_HOME
    dst = dst_root or (l0_root() / SUBPATH)
    return mirror_sqlite_tree(
        home=home,
        dst_root=dst,
        sqlite_exts=(".sqlite",),
    )
