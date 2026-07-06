"""Per-raw-ref ingest byte offsets.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

OFFSETS_FILENAME = "ingest_offsets.json"
LEGACY_OFFSETS_KEY = "__offsets__"


def default_offsets_path() -> Path:
    return l0_root() / OFFSETS_FILENAME


def offsets_path_for_state(path: Path | None = None) -> Path:
    """Return the offset file paired with an ingest_state path."""
    if path is None:
        return default_offsets_path()
    if path.name == "ingest_state.json":
        return path.with_name(OFFSETS_FILENAME)
    return path.with_name(f"{path.stem}_offsets{path.suffix}")


def load_offsets(*, path: Path | None = None) -> dict[str, int]:
    """ref -> already-consumed byte offset."""
    offsets = _load_offsets_file(offsets_path_for_state(path))
    legacy = _load_legacy_offsets(path) if path is not None else {}
    return {**legacy, **offsets}


def save_offsets(mapping: dict[str, int], *, path: Path | None = None) -> None:
    """Merge ref byte offsets into the dedicated offset file."""
    if not mapping:
        return
    target = offsets_path_for_state(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    offsets = _load_offsets_file(target)
    offsets.update({str(key): int(value) for key, value in mapping.items()})
    target.write_text(
        json.dumps(offsets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_offsets_file(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): int(value)
        for key, value in raw.items()
        if isinstance(value, (int, float))
    }


def _load_legacy_offsets(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    legacy = raw.get(LEGACY_OFFSETS_KEY)
    if not isinstance(legacy, dict):
        return {}
    return {
        str(key): int(value)
        for key, value in legacy.items()
        if isinstance(value, (int, float))
    }
