"""Cursor IDE 데이터 수집기.

소스 (macOS):
    ``~/Library/Application Support/Cursor/User/workspaceStorage/<hash>/state.vscdb``
        — workspace 별 SQLite DB (Cursor AI 채팅, 워크스페이스 상태)
    ``~/Library/Application Support/Cursor/User/globalStorage/state.vscdb``
        — 전역 설정/세션
대상:
    ``~/.synapse/private/raw/cursor/``

Cursor 실행 중일 때 SQLite 가 lock 되거나 WAL 모드일 수 있어 단순 file copy 는
안전하지 않다. :func:`sqlite3.Connection.backup` API 로 read-consistent snapshot
을 만든다 (Python 3.7+, SQLite 3.6.11+).

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.cursor.mirror import (
    DEFAULT_CURSOR_HOME,
    CollectStats,
    collect_cursor,
)

__all__ = [
    "DEFAULT_CURSOR_HOME",
    "CollectStats",
    "collect_cursor",
]
