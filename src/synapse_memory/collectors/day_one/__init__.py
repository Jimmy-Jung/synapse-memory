"""Day One (Bloom 사) journal 데이터 수집기.

소스 (macOS, Day One 3+):
    ``~/Library/Group Containers/<TEAM_ID>.dayoneapp2/...`` 아래 SQLite.
    실제 경로는 사용자 환경마다 다르므로 ``SYNAPSE_DAYONE_HOME`` 환경변수로
    override.
대상:
    ``~/.synapse/private/raw/day-one/``

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.day_one.mirror import (
    DEFAULT_DAYONE_HOME,
    ENV_DAYONE_HOME,
    CollectStats,
    collect_day_one,
)

__all__ = [
    "DEFAULT_DAYONE_HOME",
    "ENV_DAYONE_HOME",
    "CollectStats",
    "collect_day_one",
]
