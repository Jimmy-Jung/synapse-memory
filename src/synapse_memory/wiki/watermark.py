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


# 레버 2(offset ingest): 자라는 세션 jsonl을 매번 전문 재전송하지 않도록, 이미 ingest한
# byte 길이를 파일(ref)별로 기록한다. 다음 사이클은 그 offset 이후 tail만 읽는다.
# 같은 ingest_state.json에 reserved 키로 보관(소스명과 충돌 불가).
_OFFSETS_KEY = "__offsets__"


def load_offsets(*, path: Path | None = None) -> dict[str, int]:
    """ref → 이미 처리한 byte offset 매핑. 없으면 빈 dict."""
    raw = _load_all(path or default_state_path()).get(_OFFSETS_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, (int, float))}


def save_offsets(mapping: dict[str, int], *, path: Path | None = None) -> None:
    """ref별 byte offset을 병합 저장 (watermark/다른 ref 보존)."""
    if not mapping:
        return
    target = path or default_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    state = _load_all(target)
    offsets = state.get(_OFFSETS_KEY)
    if not isinstance(offsets, dict):
        offsets = {}
    offsets.update({str(k): int(v) for k, v in mapping.items()})
    state[_OFFSETS_KEY] = offsets
    target.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
