"""Shell history 수집기.

소스:
    ``~/.zsh_history``   — zsh 명령 히스토리 (EXTENDED_HISTORY 시 타임스탬프 포함)
    ``~/.bash_history``  — bash 명령 히스토리 (옵션, 존재 시만)
대상:
    ``~/.synapse/private/raw/shell-history/``

zsh ``EXTENDED_HISTORY`` 형식 예 (``:`` 로 시작):
    ``: 1715610000:0;git status``

위 형식 미사용 시 줄당 명령만 저장. 본 컬렉터는 형식 파싱 안 함 — 텍스트
append-only mirror.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.shell_history.mirror import (
    DEFAULT_BASH_HISTORY,
    DEFAULT_ZSH_HISTORY,
    CollectStats,
    collect_shell_history,
)

__all__ = [
    "DEFAULT_BASH_HISTORY",
    "DEFAULT_ZSH_HISTORY",
    "CollectStats",
    "collect_shell_history",
]
