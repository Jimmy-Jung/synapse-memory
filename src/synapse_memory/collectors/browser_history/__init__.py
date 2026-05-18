"""브라우저 history 수집기.

소스 (macOS):
    Chrome:   ``~/Library/Application Support/Google/Chrome/Default/History``
    Safari:   ``~/Library/Safari/History.db``
    Arc:      ``~/Library/Application Support/Arc/User Data/Default/History``
대상:
    ``~/.synapse/private/raw/browser-history/<browser>/History``

각 History DB 는 SQLite. ``sqlite3.Connection.backup`` 으로 read-consistent
snapshot. 브라우저 실행 중에도 안전.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.browser_history.mirror import (
    DEFAULT_BROWSERS,
    BrowserSource,
    CollectStats,
    collect_browser_history,
)

__all__ = [
    "DEFAULT_BROWSERS",
    "BrowserSource",
    "CollectStats",
    "collect_browser_history",
]
