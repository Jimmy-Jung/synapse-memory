"""Continue.dev (VS Code AI 확장) 데이터 수집기.

소스:
    ``~/.continue/sessions/*.json``  — 세션별 AI 대화 기록 (JSON)
    ``~/.continue/dev_data/*.jsonl`` — telemetry/dev event 로그 (옵션)
대상:
    ``~/.synapse/private/raw/continue/``

JSON 세션 파일은 atomic save 라 partial-write 걱정 없다. 단순 byte copy +
mtime/sha256 변경 감지 (obsidian 패턴) 으로 incremental mirror.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.continue_dev.mirror import (
    DEFAULT_CONTINUE_HOME,
    CollectStats,
    collect_continue,
)

__all__ = [
    "DEFAULT_CONTINUE_HOME",
    "CollectStats",
    "collect_continue",
]
