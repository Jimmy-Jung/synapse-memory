"""iMessage 데이터 수집기 (opt-in, PII heavy).

소스 (macOS): ``~/Library/Messages/chat.db`` (SQLite)
대상:         ``~/.synapse/private/raw/imessage/``

⚠ **Full Disk Access 필수** — macOS 시스템 설정에서 터미널(또는 Python 실행
바이너리)에 권한 부여해야 chat.db 가 읽힌다.

⚠ **PII 매우 무거움** — 본 컬렉터는 기본 활성이지만, 사용자가 비활성화하려면
``SYNAPSE_IMESSAGE_DISABLE=1`` 환경변수 설정.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.imessage.mirror import (
    DEFAULT_MESSAGES_HOME,
    ENV_DISABLE,
    CollectStats,
    collect_imessage,
)

__all__ = [
    "DEFAULT_MESSAGES_HOME",
    "ENV_DISABLE",
    "CollectStats",
    "collect_imessage",
]
