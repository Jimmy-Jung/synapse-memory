"""Per-raw-ref ingest byte offsets — append-only JSONL log (O(1) per checkpoint).

각 checkpoint가 전체 파일을 재기록하면 backfill이 O(N^2)가 된다(1파일=1RawDoc라
offset dict가 문서 수 N까지 성장, checkpoint_each가 그걸 매 doc 재기록). 대신
갱신분을 JSONL 한 줄로 append하고, load 시 last-wins로 fold한다.

읽기 호환: 신 ``.jsonl``(줄단위 fold) + 구 ``.json``(단일 dict) + ingest_state.json의
legacy ``__offsets__`` 키를 오래된→최신 순으로 병합한다(최신이 이김).

Author: JunyoungJung
Created: 2026-07-06 (2026-07-08: JSONL append-only 전환)
"""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

OFFSETS_FILENAME = "ingest_offsets.json"  # 구 단일-dict 포맷 (read-only 호환)
OFFSETS_LOG_FILENAME = "ingest_offsets.jsonl"  # 신 append-only 포맷
LEGACY_OFFSETS_KEY = "__offsets__"


def default_offsets_path() -> Path:
    return l0_root() / OFFSETS_FILENAME


def offsets_path_for_state(path: Path | None = None) -> Path:
    """구 단일-JSON offset 파일 경로 (읽기 호환용)."""
    if path is None:
        return default_offsets_path()
    if path.name == "ingest_state.json":
        return path.with_name(OFFSETS_FILENAME)
    return path.with_name(f"{path.stem}_offsets{path.suffix}")


def offsets_log_path_for_state(path: Path | None = None) -> Path:
    """신 append-only JSONL offset 로그 경로."""
    if path is None:
        return l0_root() / OFFSETS_LOG_FILENAME
    if path.name == "ingest_state.json":
        return path.with_name(OFFSETS_LOG_FILENAME)
    return path.with_name(f"{path.stem}_offsets.jsonl")


def load_offsets(*, path: Path | None = None) -> dict[str, int]:
    """ref -> already-consumed byte offset. 오래된→최신 순 병합(최신 우선)."""
    merged: dict[str, int] = {}
    if path is not None:
        merged.update(_load_legacy_offsets(path))
    merged.update(_load_offsets_file(offsets_path_for_state(path)))
    merged.update(_load_offsets_log(offsets_log_path_for_state(path)))
    return merged


def save_offsets(mapping: dict[str, int], *, path: Path | None = None) -> None:
    """갱신분을 JSONL 한 줄로 append (O(1))."""
    if not mapping:
        return
    target = offsets_log_path_for_state(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {str(key): int(value) for key, value in mapping.items()}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    # ponytail: JSONL 로그는 무한 성장 가능. load가 last-wins로 fold하므로 정확성엔
    # 무해. 파일이 과대해지면 주기적 compact(최종 상태만 1줄로 재기록) 추가.


def _load_offsets_log(path: Path) -> dict[str, int]:
    """JSONL 로그를 순서대로 fold — 같은 ref는 마지막 값이 이긴다."""
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    folded: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        for key, value in record.items():
            if isinstance(value, (int, float)):
                folded[str(key)] = int(value)
    return folded


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
