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


def test_large_doc_uses_single_budgeted_sample_call(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(
        raw_root,
        "large",
        (
            "alpha beta gamma delta epsilon\n"
            "boring filler one two three four five six seven\n"
            "/Users/jimmy/Documents/GitHub/synapse-memory/src/synapse_memory/wiki/ingest.py\n"
            "TimeoutError: integration took too long\n"
            "iota kappa lambda mu nu xi omicron"
        ),
    )
    prompts: list[str] = []
    semantic_args: list[object] = []
    timeouts: list[int] = []
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHAR_THRESHOLD", 25, raising=False)
    monkeypatch.setattr(ingest_mod, "SAMPLED_DOC_CHAR_LIMIT", 500, raising=False)
    monkeypatch.setattr(ingest_mod, "SAMPLED_DOC_CHAR_BUDGET", 600, raising=False)
    monkeypatch.setattr(ingest_mod, "SAMPLED_DOC_EDGE_CHARS", 45, raising=False)
    monkeypatch.setattr(ingest_mod, "SAMPLED_DOC_SIGNAL_CHARS", 220, raising=False)

    def fake_related(text, *, vault_path=None, pages=None, semantic_fn="default"):
        semantic_args.append(semantic_fn)
        return []

    def fake_complete(prompt, *, system=None, model=None, json_schema=None, env=None, timeout=120, **kw):
        prompts.append(prompt)
        timeouts.append(timeout)
        return {"operations": []}

    monkeypatch.setattr(ingest_mod, "find_related_pages", fake_related)
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
    assert len(prompts) == 1
    assert semantic_args == [None]
    assert timeouts == [300]
    assert "alpha beta gamma delta" in prompts[0]
    assert "TimeoutError" in prompts[0]
    assert "iota kappa lambda" in prompts[0]
    assert len(prompts[0]) < 1_200


def test_small_doc_can_disable_semantic_retrieval(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "small", "short project update")
    semantic_args: list[object] = []

    def fake_related(text, *, vault_path=None, pages=None, semantic_fn="default"):
        semantic_args.append(semantic_fn)
        return []

    monkeypatch.setattr(ingest_mod, "find_related_pages", fake_related)
    monkeypatch.setattr(
        ingest_mod.ai_api,
        "complete_structured",
        _fake_complete_structured({"operations": []}),
    )
    result = ingest_source(
        "claude-code",
        vault_path=tmp_path,
        raw_root=raw_root,
        watermark_path=tmp_path / "state.json",
        ai_env=None,
        today="2026-06-14",
        semantic_retrieval=False,
    )

    assert result.docs_processed == 1
    assert semantic_args == [None]


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


def test_large_doc_provider_error_is_sanitized_in_log(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "large", "alpha beta gamma delta epsilon zeta")
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHAR_THRESHOLD", 25, raising=False)

    def provider_error(*args, **kwargs):
        raise RuntimeError(
            '{"error":{"message":"rate limited","type":"rate_limit_error"},'
            '"session_id":"sess_secret","usage":{"input_tokens":999}}'
        )

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", provider_error)
    result = ingest_source(
        "claude-code",
        vault_path=tmp_path,
        raw_root=raw_root,
        watermark_path=state,
        ai_env=None,
        today="2026-06-14",
        checkpoint_each=True,
    )

    text = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert result.docs_skipped == 1
    assert "rate limited" in text
    assert "rate_limit_error" in text
    assert "sess_secret" not in text
    assert "input_tokens" not in text


def test_small_doc_provider_error_is_sanitized_in_result_errors(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "small", "short project update")

    def provider_error(*args, **kwargs):
        raise RuntimeError(
            '{"error":{"message":"rate limited","type":"rate_limit_error"},'
            '"session_id":"sess_secret","usage":{"input_tokens":999}}'
        )

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", provider_error)
    result = ingest_source(
        "claude-code",
        vault_path=tmp_path,
        raw_root=raw_root,
        watermark_path=tmp_path / "state.json",
        ai_env=None,
        today="2026-06-14",
    )

    assert len(result.errors) == 1
    assert "rate limited" in result.errors[0]
    assert "sess_secret" not in result.errors[0]
    assert "input_tokens" not in result.errors[0]


def test_oversize_doc_skips_without_llm_and_advances_watermark(tmp_path, monkeypatch) -> None:
    import os
    from datetime import datetime

    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "oversize", "alpha " * 100)
    session_path = raw_root / "oversize.jsonl"
    mtime = 1_700_000_100
    os.utime(session_path, (mtime, mtime))
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod, "LARGE_DOC_CHAR_THRESHOLD", 25, raising=False)
    monkeypatch.setattr(ingest_mod, "SAMPLED_DOC_CHAR_LIMIT", 80, raising=False)

    def unexpected_llm_call(*args, **kwargs):
        raise AssertionError("oversize doc must not call LLM")

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", unexpected_llm_call)
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
    assert "skipped oversize doc" in (tmp_path / "log.md").read_text(encoding="utf-8")
