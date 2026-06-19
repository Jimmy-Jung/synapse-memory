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


def test_ingest_error_isolation(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "aaa", "first doc")
    _write_session(raw_root, "bbb", "second doc")
    state = tmp_path / "state.json"
    calls = {"n": 0}

    def flaky(prompt, *, system=None, model=None, json_schema=None, env=None, timeout=120, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"operations": [
            {"op": "create", "type": "concept", "slug": "ok", "title": "OK", "body": "b"}]}

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", flaky)
    result = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                           watermark_path=state, ai_env=None, today="2026-06-14")
    assert result.docs_processed == 2
    assert len(result.errors) == 1
    assert "ok" in result.pages_written


def test_large_doc_is_chunked_for_integration_calls(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(
        raw_root,
        "large",
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda",
    )
    prompts: list[str] = []
    timeouts: list[int] = []
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHAR_THRESHOLD", 25, raising=False)
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHUNK_TOKENS", 4, raising=False)
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHUNK_OVERLAP", 0, raising=False)

    def fake_complete(prompt, *, system=None, model=None, json_schema=None, env=None, timeout=120, **kw):
        prompts.append(prompt)
        timeouts.append(timeout)
        return {"operations": []}

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", fake_complete)
    result = ingest_source(
        "claude-code",
        vault_path=tmp_path,
        raw_root=raw_root,
        watermark_path=tmp_path / "state.json",
        ai_env=None,
        today="2026-06-14",
    )

    assert result.docs_processed == 1
    assert result.docs_skipped == 0
    assert len(prompts) == 3
    assert timeouts == [300, 300, 300]
    assert "alpha beta gamma delta" in prompts[0]
    assert "epsilon zeta eta theta" in prompts[1]
    assert "iota kappa lambda" in prompts[2]


def test_large_doc_failure_is_skipped_and_advances_watermark(tmp_path, monkeypatch) -> None:
    import os
    from datetime import datetime

    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "large", "alpha beta gamma delta epsilon zeta")
    session_path = raw_root / "large.jsonl"
    mtime = 1_700_000_000
    os.utime(session_path, (mtime, mtime))
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHAR_THRESHOLD", 25, raising=False)
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHUNK_TOKENS", 4, raising=False)
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHUNK_OVERLAP", 0, raising=False)

    def timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", timeout)
    result = ingest_source(
        "claude-code",
        vault_path=tmp_path,
        raw_root=raw_root,
        watermark_path=state,
        ai_env=None,
        today="2026-06-14",
        checkpoint_each=True,
    )

    expected = datetime.fromtimestamp(mtime).isoformat(timespec="microseconds")
    assert result.docs_processed == 1
    assert result.docs_skipped == 1
    assert result.errors == []
    assert load_watermark("claude-code", path=state) == expected
    assert "skipped large doc" in (tmp_path / "log.md").read_text(encoding="utf-8")
