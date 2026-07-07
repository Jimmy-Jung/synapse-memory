"""raw mirror compact/rehydrate 회귀 테스트.

저자: JunyoungJung
작성일: 2026-07-03
"""
from __future__ import annotations

import base64
import gzip
import json
import os
from datetime import datetime
from pathlib import Path

from synapse_memory.collectors.claude_code.mirror import (
    OFFSETS_DIR,
    collect_claude_code,
)
from synapse_memory.wiki.compact import (
    SIDECAR_SUFFIX,
    compact_bytes,
    compact_mirror_source,
    rehydrate,
)
from synapse_memory.wiki.offsets import load_offsets, offsets_path_for_state, save_offsets
from synapse_memory.wiki.rawdoc import iter_new_raw
from synapse_memory.wiki.watermark import save_watermark


def _json_line(event: dict) -> bytes:
    return json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"


def _append_jsonl(path: Path, *events: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(_json_line(event) for event in events)
    with open(path, "ab") as handle:
        handle.write(payload)
    return payload


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="microseconds")


def test_compact_apply_then_collect_tail_then_rehydrate_roundtrip(tmp_path: Path) -> None:
    claude_home = tmp_path / "claude"
    mirror_root = tmp_path / "l0" / "raw" / "claude-code"
    state_path = tmp_path / "ingest_state.json"
    source = claude_home / "projects" / "demo" / "session.jsonl"

    _append_jsonl(
        source,
        {"cwd": "/repo"},
        {"message": {"role": "user", "content": "첫 turn"}},
        {"message": {"role": "assistant", "content": [{"type": "text", "text": "응답"}]}},
        {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]}},
        {"type": "tool_result", "content": "dead weight"},
    )
    collect_claude_code(claude_home=claude_home, dst_root=mirror_root)
    mirror = mirror_root / "projects" / "demo" / "session.jsonl"
    original = mirror.read_bytes()
    collector_offset = mirror_root / OFFSETS_DIR / "projects__demo__session.jsonl.offset"
    collector_offset_before = collector_offset.read_text(encoding="utf-8")

    old_ts = 1_700_000_000.123456
    os.utime(mirror, (old_ts, old_ts))
    ref = "claude-code:projects/demo/session.jsonl"
    save_watermark("claude-code", _iso(old_ts), path=state_path)
    save_offsets({ref: mirror.stat().st_size}, path=state_path)
    original_mtime_ns = mirror.stat().st_mtime_ns

    result = compact_mirror_source(
        "claude-code",
        root=mirror_root,
        watermark_path=state_path,
        apply=True,
    )

    assert result.files_seen == 1
    assert result.files_changed == 1
    assert mirror.stat().st_size < len(original)
    assert mirror.stat().st_mtime_ns == original_mtime_ns
    assert load_offsets(path=state_path)[ref] == mirror.stat().st_size
    assert offsets_path_for_state(state_path).is_file()
    assert "__offsets__" not in json.loads(state_path.read_text(encoding="utf-8"))
    assert collector_offset.read_text(encoding="utf-8") == collector_offset_before
    sidecar = mirror.with_name(mirror.name + SIDECAR_SUFFIX)
    assert sidecar.is_file()
    with gzip.open(sidecar, "rt", encoding="utf-8") as handle:
        next(handle)
        dropped_raw = b"".join(
            base64.b64decode(json.loads(line)["raw_b64"])
            for line in handle
        )
    assert b"tool_result" in dropped_raw

    settled_docs = list(
        iter_new_raw(
            "claude-code",
            since=_iso(old_ts),
            root=mirror_root,
            offsets=load_offsets(path=state_path),
        )
    )
    assert settled_docs == []

    new_line = _append_jsonl(
        source,
        {"message": {"role": "user", "content": "새 turn"}},
    )
    collect_claude_code(claude_home=claude_home, dst_root=mirror_root)
    docs = list(
        iter_new_raw(
            "claude-code",
            since=_iso(old_ts),
            root=mirror_root,
            offsets=load_offsets(path=state_path),
        )
    )
    assert len(docs) == 1
    assert "새 turn" in docs[0].text
    assert "첫 turn" not in docs[0].text

    restored = rehydrate(
        "claude-code",
        root=mirror_root,
        watermark_path=state_path,
        apply=True,
    )
    assert restored.files_changed == 1
    assert mirror.read_bytes() == original + new_line
    assert not sidecar.exists()
    assert load_offsets(path=state_path)[ref] == len(original + new_line)


def test_compact_dry_run_does_not_write_files(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "codex"
    mirror = root / "sessions" / "2026" / "07" / "03" / "rollout.jsonl"
    mirror.parent.mkdir(parents=True)
    mirror.write_bytes(
        b'{"type":"session_meta","payload":{"id":"s"}}\n'
        b'{"type":"compacted","payload":{"message":"drop"}}\n'
    )
    old_ts = 1_700_000_001.0
    os.utime(mirror, (old_ts, old_ts))
    state_path = tmp_path / "state.json"
    ref = "codex:sessions/2026/07/03/rollout.jsonl"
    save_watermark("codex", _iso(old_ts), path=state_path)
    save_offsets({ref: mirror.stat().st_size}, path=state_path)
    before = mirror.read_bytes()

    result = compact_mirror_source(
        "codex",
        root=root,
        watermark_path=state_path,
        apply=False,
    )

    assert result.files_eligible == 1
    assert result.bytes_reclaimable > 0
    assert mirror.read_bytes() == before
    assert not mirror.with_name(mirror.name + SIDECAR_SUFFIX).exists()


def test_codex_keep_predicate_is_strict_whitelist() -> None:
    compacted = compact_bytes(
        "codex",
        b"".join(
            [
                _json_line({"type": "session_meta", "payload": {"cwd": "/repo"}}),
                _json_line({"type": "compacted", "payload": {"text": "drop compacted"}}),
                _json_line({"type": "custom_tool_call", "payload": {"text": "drop custom"}}),
                _json_line({"type": "event_msg", "payload": {"type": "user_message", "message": "keep user"}}),
                _json_line({"type": "event_msg", "payload": {"type": "agent_message", "message": "drop agent"}}),
                _json_line({"type": "response_item", "payload": {"type": "message", "role": "user"}}),
                _json_line({"type": "response_item", "payload": {"type": "message", "role": "assistant"}}),
                _json_line({"type": "response_item", "payload": {"type": "reasoning", "text": "drop reasoning"}}),
            ]
        ),
    )

    kept = compacted.kept.decode("utf-8")
    dropped = b"".join(item.raw for item in compacted.dropped).decode("utf-8")
    assert "session_meta" in kept
    assert "keep user" in kept
    assert '"role": "user"' in kept
    assert '"role": "assistant"' in kept
    assert "drop compacted" in dropped
    assert "drop custom" in dropped
    assert "drop agent" in dropped
    assert "drop reasoning" in dropped
