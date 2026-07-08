"""ingest offset storage — append-only JSONL 로그 + 읽기 호환."""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.wiki.offsets import (
    load_offsets,
    offsets_log_path_for_state,
    offsets_path_for_state,
    save_offsets,
)
from synapse_memory.wiki.watermark import save_watermark


def _log_records(state: Path) -> list[dict[str, int]]:
    text = offsets_log_path_for_state(state).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_offsets_use_separate_file_from_watermark(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    ref = "codex:sessions/rollout.jsonl"

    save_watermark("codex", "2026-07-06T10:00:00", path=state)
    save_offsets({ref: 42}, path=state)

    # watermark 파일은 offset과 섞이지 않는다.
    assert json.loads(state.read_text(encoding="utf-8")) == {
        "codex": "2026-07-06T10:00:00"
    }
    # offset은 append-only JSONL 로그에 기록된다.
    assert _log_records(state) == [{ref: 42}]
    assert load_offsets(path=state) == {ref: 42}


def test_offsets_append_only_last_wins(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    ref = "codex:sessions/rollout.jsonl"

    save_offsets({ref: 10}, path=state)
    save_offsets({ref: 25}, path=state)
    save_offsets({"other:log.jsonl": 5}, path=state)

    # 재기록이 아니라 append: 3줄. checkpoint가 O(1)임을 방증.
    assert len(_log_records(state)) == 3
    # fold 결과는 ref별 마지막 값.
    assert load_offsets(path=state) == {ref: 25, "other:log.jsonl": 5}


def test_offsets_jsonl_overrides_legacy_json(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    # 업그레이드 전 남아있는 구 단일-dict .json.
    offsets_path_for_state(state).write_text(
        json.dumps({"a": 1, "b": 2}), encoding="utf-8"
    )
    save_offsets({"a": 99}, path=state)  # 신 로그가 같은 ref를 덮어씀.

    assert load_offsets(path=state) == {"a": 99, "b": 2}


def test_offsets_read_legacy_reserved_key(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    state.write_text(
        json.dumps({"codex": "2026-07-06T10:00:00", "__offsets__": {"ref": 7}}),
        encoding="utf-8",
    )

    assert load_offsets(path=state) == {"ref": 7}


def test_save_offsets_empty_is_noop(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    save_offsets({}, path=state)
    assert not offsets_log_path_for_state(state).exists()
    assert load_offsets(path=state) == {}
