"""ingest offset storage."""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.wiki.offsets import (
    load_offsets,
    offsets_path_for_state,
    save_offsets,
)
from synapse_memory.wiki.watermark import save_watermark


def test_offsets_use_separate_file_from_watermark(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    ref = "codex:sessions/rollout.jsonl"

    save_watermark("codex", "2026-07-06T10:00:00", path=state)
    save_offsets({ref: 42}, path=state)

    assert json.loads(state.read_text(encoding="utf-8")) == {
        "codex": "2026-07-06T10:00:00"
    }
    assert json.loads(offsets_path_for_state(state).read_text(encoding="utf-8")) == {
        ref: 42
    }
    assert load_offsets(path=state) == {ref: 42}


def test_offsets_read_legacy_reserved_key(tmp_path: Path) -> None:
    state = tmp_path / "ingest_state.json"
    state.write_text(
        json.dumps({"codex": "2026-07-06T10:00:00", "__offsets__": {"ref": 7}}),
        encoding="utf-8",
    )

    assert load_offsets(path=state) == {"ref": 7}
