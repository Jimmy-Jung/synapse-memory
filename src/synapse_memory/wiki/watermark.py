# src/synapse_memory/wiki/watermark.py
"""ingest 진행상태 — 소스별 마지막 처리 시각(ISO).

저장: ``~/.synapse/private/ingest_state.json`` (l0_root 하위).
형식: {"<source>": "<iso8601>"}.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

STATE_FILENAME = "ingest_state.json"


def default_state_path() -> Path:
    return l0_root() / STATE_FILENAME


def _load_all(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_watermark(source: str, *, path: Path | None = None) -> str | None:
    """소스의 마지막 처리 ISO 시각. 없으면 None."""
    state = _load_all(path or default_state_path())
    value = state.get(source)
    return str(value) if value else None


def save_watermark(source: str, iso: str, *, path: Path | None = None) -> None:
    """소스의 처리 시각 갱신 (다른 소스 보존)."""
    target = path or default_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    state = _load_all(target)
    state[source] = iso
    target.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
