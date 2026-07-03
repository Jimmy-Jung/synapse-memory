"""Aider (terminal AI pair-programmer) 데이터 수집기.

소스:
    ``~/.aider.chat.history.md``  — markdown 대화 기록 (append-only)
    ``~/.aider.input.history``    — 사용자 입력 줄 기록 (append-only)
대상:
    ``~/.synapse/private/raw/aider/``

``mirror_jsonl`` 의 newline-terminated record 처리를 재사용한다. markdown 도
줄 단위 stream 으로 mirror 가능 (마크다운 구조 보존은 후속 단계의 책임).

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.aider.mirror import (
    DEFAULT_CHAT_HISTORY,
    DEFAULT_INPUT_HISTORY,
    CollectStats,
    collect_aider,
)

__all__ = [
    "DEFAULT_CHAT_HISTORY",
    "DEFAULT_INPUT_HISTORY",
    "CollectStats",
    "collect_aider",
]
