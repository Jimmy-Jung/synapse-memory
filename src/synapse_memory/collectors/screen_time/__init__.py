"""macOS Screen Time / app usage 수집기.

소스: ``~/Library/Application Support/Knowledge/knowledgeC.db`` (SQLite)
대상: ``~/.synapse/private/raw/screen-time/knowledgeC.db``

CoreDuet 의 ``knowledgeC.db`` 는 macOS 가 앱 사용 시간, 위치, alerts 등을 통합
저장하는 DB. 본 컬렉터는 전체 DB 를 그대로 backup. 어떤 stream 을 사용할지는
후속 단계 (예: ``ZOBJECT WHERE ZSTREAMNAME='/app/usage'``) 의 책임.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.screen_time.mirror import (
    DEFAULT_KNOWLEDGEC_DB,
    CollectStats,
    collect_screen_time,
)

__all__ = [
    "DEFAULT_KNOWLEDGEC_DB",
    "CollectStats",
    "collect_screen_time",
]
