"""Apple Health export 수집기.

소스:
    사용자가 iOS Health 앱에서 수동 export 한 ``export*.zip``.
    기본 drop-in 디렉토리: ``~/Downloads`` (env ``SYNAPSE_HEALTH_DROP`` 으로 override).
대상:
    ``~/.synapse/private/raw/apple-health/<filename>``

다른 컬렉터와 달리 사용자가 수동으로 export 해서 디렉토리에 떨어뜨려야 한다.
unzip + XML 파싱은 후속 단계의 책임 — 본 컬렉터는 zip 자체를 안전한 위치로
mirror 만.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.apple_health.mirror import (
    DEFAULT_DROP_DIR,
    ENV_DROP_DIR,
    CollectStats,
    collect_apple_health,
)

__all__ = [
    "DEFAULT_DROP_DIR",
    "ENV_DROP_DIR",
    "CollectStats",
    "collect_apple_health",
]
