"""ingest 실패 카운트 / dead-letter 스토어 테스트.

Author: JunyoungJung
Created: 2026-07-08
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.failures import (
    MAX_INGEST_FAILURES,
    clear_failure,
    failures_path_for_state,
    load_failures,
    record_failure,
)


def test_record_increments_and_persists(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    ref = "codex:sessions/2026/07/01/rollout-x.jsonl"

    assert record_failure(ref, path=state) == 1
    assert record_failure(ref, path=state) == 2
    assert load_failures(path=state)[ref] == 2
    # 별도 파일에 저장(ingest_state와 짝)
    assert failures_path_for_state(state).name == "ingest_failures.json"
    assert failures_path_for_state(state).is_file()


def test_clear_removes_ref(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    ref = "claude-code:projects/x.jsonl"
    record_failure(ref, path=state)
    clear_failure(ref, path=state)
    assert ref not in load_failures(path=state)
    # 없는 ref clear는 no-op
    clear_failure("missing", path=state)


def test_threshold_reached_after_max(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    ref = "codex:big-doc.jsonl"
    counts = [record_failure(ref, path=state) for _ in range(MAX_INGEST_FAILURES)]
    assert counts[-1] >= MAX_INGEST_FAILURES  # dead-letter 트리거 조건 도달
