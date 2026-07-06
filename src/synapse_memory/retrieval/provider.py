"""AI provider resolution shared by retrieval and ingest.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from typing import Literal

ProviderName = Literal["claude", "codex"]


def _provider() -> ProviderName | None:
    """Return configured provider. ``auto`` stays ``None`` for runtime detection."""
    try:
        from synapse_memory.config import get_config

        requested = get_config().ai_provider.lower()
    except Exception:
        return None
    if requested == "claude":
        return "claude"
    if requested == "codex":
        return "codex"
    return None

