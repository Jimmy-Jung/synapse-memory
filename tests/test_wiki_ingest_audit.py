# tests/test_wiki_ingest_audit.py
"""ingest-audit — LLM 호출 없이 pending raw 비용을 예측한다."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import synapse_memory.wiki.ingest_routing as routing_mod
from synapse_memory.wiki.ingest_audit import audit_ingest_queue


def _write_session(root: Path, name: str, text: str, mtime: int) -> None:
    path = root / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"message": {"role": "user", "content": text}}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    os.utime(path, (mtime, mtime))


def test_audit_classifies_pending_docs_without_llm(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "small", "a" * 10, 1_700_000_000)
    _write_session(raw_root, "sampled", "b" * 50, 1_700_000_010)
    _write_session(raw_root, "oversize", "c" * 90, 1_700_000_020)
    monkeypatch.setattr(routing_mod, "LARGE_DOC_CHAR_THRESHOLD", 20)
    monkeypatch.setattr(routing_mod, "SAMPLED_DOC_CHAR_LIMIT", 70)
    result = audit_ingest_queue(
        "claude-code",
        raw_root=raw_root,
        watermark_path=tmp_path / "state.json",
    )

    assert result.docs_pending == 3
    assert result.docs_small == 1
    assert result.docs_sampled == 1
    assert result.docs_oversize == 1
    assert result.estimated_llm_calls == 3
    assert result.max_chars == 90
    assert result.privacy_mode == "raw_or_sampled_raw_to_provider"
    assert result.provider_payload == "small_raw_or_sampled_raw"
    assert "sampled docs send" in result.privacy_note


def test_audit_can_estimate_without_semantic_retrieval(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "small", "a" * 10, 1_700_000_000)
    _write_session(raw_root, "sampled", "b" * 50, 1_700_000_010)
    _write_session(raw_root, "oversize", "c" * 90, 1_700_000_020)
    monkeypatch.setattr(routing_mod, "LARGE_DOC_CHAR_THRESHOLD", 20)
    monkeypatch.setattr(routing_mod, "SAMPLED_DOC_CHAR_LIMIT", 70)

    result = audit_ingest_queue(
        "claude-code",
        raw_root=raw_root,
        watermark_path=tmp_path / "state.json",
        semantic_retrieval=False,
    )

    assert result.docs_pending == 3
    assert result.estimated_llm_calls == 2


def test_audit_respects_watermark_and_limit(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    state = tmp_path / "state.json"
    _write_session(raw_root, "old", "a" * 10, 1_700_000_000)
    _write_session(raw_root, "first", "b" * 10, 1_700_000_010)
    _write_session(raw_root, "second", "c" * 10, 1_700_000_020)
    since = datetime.fromtimestamp(1_700_000_000).isoformat(timespec="microseconds")
    state.write_text(json.dumps({"claude-code": since}), encoding="utf-8")
    monkeypatch.setattr(routing_mod, "LARGE_DOC_CHAR_THRESHOLD", 20)

    result = audit_ingest_queue(
        "claude-code",
        raw_root=raw_root,
        watermark_path=state,
        limit=1,
    )

    assert result.docs_pending == 1
    assert result.docs_small == 1
    assert result.docs_sampled == 0
    assert result.docs_oversize == 0
    assert result.estimated_llm_calls == 2
