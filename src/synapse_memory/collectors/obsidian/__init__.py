"""Obsidian vault 수집기.

소스: ``~/Library/Mobile Documents/iCloud~md~obsidian/Documents``
대상: ``~/.synapse/private/raw/obsidian/``

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors._filestate import FileState
from synapse_memory.collectors.obsidian.mirror import (
    DEFAULT_VAULT_PATH,
    ENV_VAR_VAULT,
    EXCLUDED_DIRS,
    CollectStats,
    collect_obsidian,
    get_vault_path,
)

__all__ = [
    "DEFAULT_VAULT_PATH",
    "ENV_VAR_VAULT",
    "EXCLUDED_DIRS",
    "CollectStats",
    "FileState",
    "collect_obsidian",
    "get_vault_path",
]
