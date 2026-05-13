"""Claude Code 데이터 수집기.

소스: ``~/.claude/projects/<cwd-slug>/<sessionId>.jsonl`` + ``~/.claude/history.jsonl``
대상: ``~/.synapse/private/raw/claude-code/``

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.claude_code.mirror import (
    CollectStats,
    DEFAULT_CLAUDE_HOME,
    collect_claude_code,
    mirror_jsonl,
)

__all__ = [
    "CollectStats",
    "DEFAULT_CLAUDE_HOME",
    "collect_claude_code",
    "mirror_jsonl",
]
