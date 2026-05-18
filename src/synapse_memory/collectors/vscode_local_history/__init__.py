"""VS Code Local History 수집기.

소스 (macOS):
    ``~/Library/Application Support/Code/User/History/<dir-hash>/<timestamp>.<ext>``
    ``~/Library/Application Support/Code/User/History/<dir-hash>/entries.json``
대상:
    ``~/.synapse/private/raw/vscode-local-history/``

VS Code 가 파일 저장 시점마다 자동으로 만드는 versioned snapshot. 사용자가
"내가 어떻게 코드를 다듬어 갔는가"를 회상할 때 가치 있음.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.vscode_local_history.mirror import (
    DEFAULT_VSCODE_HISTORY,
    CollectStats,
    collect_vscode_local_history,
)

__all__ = [
    "DEFAULT_VSCODE_HISTORY",
    "CollectStats",
    "collect_vscode_local_history",
]
