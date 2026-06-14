"""Day One → L0 mirror.

소스: ``~/Library/Group Containers/<TEAM_ID>.dayoneapp2/`` 아래 SQLite.
``SYNAPSE_DAYONE_HOME`` 환경변수가 있으면 그 경로를 그대로 사용.

대상: ``~/.synapse/private/raw/day-one/`` 아래 상대 경로 보존.

공통 ``_sqlite_mirror.mirror_sqlite_tree`` 헬퍼 사용.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import os
from pathlib import Path

from synapse_memory.collectors._sqlite_mirror import (
    SqliteCollectStats as CollectStats,
)
from synapse_memory.collectors._sqlite_mirror import (
    mirror_sqlite_tree,
)
from synapse_memory.storage.l0 import l0_root

ENV_DAYONE_HOME = "SYNAPSE_DAYONE_HOME"

DEFAULT_DAYONE_PARENT = Path.home() / "Library" / "Group Containers"
DAYONE_DIR_PATTERN = "*.dayoneapp2"
SUBPATH = Path("raw") / "day-one"

__all__ = [
    "DAYONE_DIR_PATTERN",
    "DEFAULT_DAYONE_HOME",
    "DEFAULT_DAYONE_PARENT",
    "ENV_DAYONE_HOME",
    "SUBPATH",
    "CollectStats",
    "collect_day_one",
]


def _resolve_default_home() -> Path | None:
    """``~/Library/Group Containers/*.dayoneapp2`` 가운데 첫 번째.

    여러 개 있으면 사용자가 ``SYNAPSE_DAYONE_HOME`` 으로 명시해야 함.
    """
    if not DEFAULT_DAYONE_PARENT.is_dir():
        return None
    matches = sorted(DEFAULT_DAYONE_PARENT.glob(DAYONE_DIR_PATTERN))
    return matches[0] if matches else None


DEFAULT_DAYONE_HOME: Path | None = _resolve_default_home()


def collect_day_one(
    *,
    dayone_home: Path | None = None,
    dayone_home_env: str | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Day One 데이터 1회 수집 (incremental).

    Args:
        dayone_home: explicit override (테스트용 우선).
        dayone_home_env: ``SYNAPSE_DAYONE_HOME`` env 값 override (테스트용).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/day-one``).

    Resolution 순서:
        1. ``dayone_home`` 인자.
        2. ``dayone_home_env`` 인자 또는 ``SYNAPSE_DAYONE_HOME`` env.
        3. ``DEFAULT_DAYONE_HOME`` (glob 결과).

    Returns:
        CollectStats — 처리 통계. resolution 실패 시 errors 없이 빈 통계 반환
        (Day One 미설치 — 정상).
    """
    home: Path | None
    if dayone_home is not None:
        home = dayone_home
    else:
        env_val = (
            dayone_home_env
            if dayone_home_env is not None
            else os.environ.get(ENV_DAYONE_HOME)
        )
        home = Path(env_val).expanduser() if env_val else DEFAULT_DAYONE_HOME

    dst = dst_root or (l0_root() / SUBPATH)

    if home is None:
        return CollectStats()  # Day One 미설치 — silent

    return mirror_sqlite_tree(
        home=home,
        dst_root=dst,
    )
