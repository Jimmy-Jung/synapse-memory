#!/usr/bin/env python3
"""
Shared path configuration for the Synapse Memory plugin.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import os
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ENV_VAULT_AI_ROOT = "SYNAPSE_VAULT_AI_ROOT"
ENV_RUNTIME_ROOT = "SYNAPSE_RUNTIME_ROOT"


def runtime_root() -> Path:
    return Path(os.environ.get(ENV_RUNTIME_ROOT, str(Path.home() / ".synapse"))).expanduser()


def private_root() -> Path:
    return runtime_root() / "private"


def default_vault_ai_root() -> Path:
    return Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "90_System" / "AI"


def vault_ai_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    env = os.environ.get(ENV_VAULT_AI_ROOT)
    if env:
        return Path(env).expanduser()
    return default_vault_ai_root()


def memory_inbox_dir(explicit_ai_root: Path | None = None) -> Path:
    return vault_ai_root(explicit_ai_root) / "MemoryInbox"


def memory_review_path(explicit_ai_root: Path | None = None) -> Path:
    return vault_ai_root(explicit_ai_root) / "MemoryReview.md"


def profile_path(explicit_ai_root: Path | None = None) -> Path:
    return vault_ai_root(explicit_ai_root) / "Profile.md"


def decision_patterns_path(explicit_ai_root: Path | None = None) -> Path:
    return vault_ai_root(explicit_ai_root) / "DecisionPatterns.md"


def decision_quality_registry_path(explicit_ai_root: Path | None = None) -> Path:
    return vault_ai_root(explicit_ai_root) / "DecisionQualityRegistry.md"


def validate_vault_ai_root(path: Path) -> list[str]:
    required = [
        path / "MemoryInbox",
        path / "Profile.md",
        path / "DecisionPatterns.md",
        path / "DecisionQualityRegistry.md",
    ]
    return [str(item) for item in required if not item.exists()]
