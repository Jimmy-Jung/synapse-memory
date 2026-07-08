"""Per-raw-ref ingest 실패 카운트 — 연속 실패 doc을 dead-letter로 격리한다.

작은 doc이 provider 오류(예: codex 타임아웃)로 계속 실패하면 스칼라 watermark가
영구 동결되고 무한 재시도된다. ref별 실패 횟수를 세어 MAX_INGEST_FAILURES를
넘으면 skip(dead-letter) 처리해 소스가 굶지 않게 한다.

Author: JunyoungJung
Created: 2026-07-08
"""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

FAILURES_FILENAME = "ingest_failures.json"
# 이 횟수만큼 연속 실패하면 dead-letter (watermark 전진 + skip 집계).
MAX_INGEST_FAILURES = 2


def default_failures_path() -> Path:
    return l0_root() / FAILURES_FILENAME


def failures_path_for_state(path: Path | None = None) -> Path:
    """ingest_state 경로와 짝을 이루는 실패 카운트 파일."""
    if path is None:
        return default_failures_path()
    if path.name == "ingest_state.json":
        return path.with_name(FAILURES_FILENAME)
    return path.with_name(f"{path.stem}_failures{path.suffix}")


def load_failures(*, path: Path | None = None) -> dict[str, int]:
    return _load(failures_path_for_state(path))


def record_failure(ref: str, *, path: Path | None = None) -> int:
    """ref 실패 횟수 +1 후 저장. 새 카운트 반환."""
    target = failures_path_for_state(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _load(target)
    data[ref] = data.get(ref, 0) + 1
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data[ref]


def clear_failure(ref: str, *, path: Path | None = None) -> None:
    """소비 확정(성공/dead-letter)된 ref의 실패 기록 제거. 없으면 no-op."""
    target = failures_path_for_state(path)
    data = _load(target)
    if ref not in data:
        return
    del data[ref]
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(path: Path) -> dict[str, int]:
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
