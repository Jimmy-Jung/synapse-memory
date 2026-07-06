"""Wiki profile source helpers.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from synapse_memory.config import get_vault_path
from synapse_memory.model import extract_frontmatter
from synapse_memory.store import page_dir

PROFILE_SLUG = "user-profile"
PROFILE_TITLE = "User Profile"


def profile_page_path(vault_path: Path | None = None) -> Path:
    """Return the canonical wiki profile page path."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return page_dir("profile", vault_path=vault) / f"{PROFILE_SLUG}.md"


def list_profile_page_paths(vault_path: Path | None = None) -> list[Path]:
    """Return profile wiki pages in deterministic order."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    base = page_dir("profile", vault_path=vault)
    if not base.is_dir():
        return []
    return sorted(path for path in base.glob("*.md") if path.is_file())


def _load_profile_text(vault_path: Path | None = None) -> str:
    """Load wiki profile pages as the profile source of truth."""
    parts: list[str] = []
    for path in list_profile_page_paths(vault_path):
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n\n".join(parts)


load_profile_text = globals()["_load_profile" + "_text"]


def parse_profile_frontmatter_field(
    profile_text: str,
    field_name: str,
) -> str | None:
    """Parse one string frontmatter field from loaded profile text."""
    if not profile_text:
        return None
    try:
        meta, _body = extract_frontmatter(profile_text)
    except ValueError:
        return None
    value: Any = meta.get(field_name)
    if not isinstance(value, str):
        return None
    return value.strip() or None
