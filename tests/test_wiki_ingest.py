# tests/test_wiki_ingest.py
"""ingest_source 오케스트레이션 (LLM은 monkeypatch)."""
from __future__ import annotations

import json
from pathlib import Path

import synapse_memory.wiki.ingest as ingest_mod
from synapse_memory.wiki.ingest import ingest_source
from synapse_memory.wiki.page import load_page
from synapse_memory.wiki.watermark import load_watermark


def _write_session(root: Path, name: str, user_text: str) -> None:
    f = root / f"{name}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps({"message": {"role": "user", "content": user_text}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _fake_complete_structured(ops_payload):
    def _fn(prompt, *, system=None, model=None, json_schema=None, env=None, timeout=120, **kw):
        return ops_payload
    return _fn


def test_ingest_creates_page_and_updates_watermark(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "sess1", "Synapse Memory 프로젝트 시작")
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured",
        _fake_complete_structured({"operations": [
            {"op": "create", "type": "project", "slug": "synapse-memory",
             "title": "Synapse Memory", "body": "프로젝트 본문", "related": [], "sources": []}]}))
    result = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                           watermark_path=state, ai_env=None, today="2026-06-14")
    assert result.docs_processed == 1
    assert "synapse-memory" in result.pages_written
    assert load_page("project", "synapse-memory", vault_path=tmp_path).title == "Synapse Memory"
    again = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                          watermark_path=state, ai_env=None, today="2026-06-14")
    assert again.docs_processed == 0


def test_ingest_dry_run_writes_nothing(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "s", "RAG 개념 정리")
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured",
        _fake_complete_structured({"operations": [
            {"op": "create", "type": "concept", "slug": "rag", "title": "RAG", "body": "b"}]}))
    result = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                           watermark_path=state, ai_env=None, dry_run=True, today="2026-06-14")
    assert result.pages_written == []
    assert not (tmp_path / "Concepts" / "rag.md").exists()
    assert load_watermark("claude-code", path=state) is None
