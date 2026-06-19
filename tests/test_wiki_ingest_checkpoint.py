# tests/test_wiki_ingest_checkpoint.py
"""checkpoint_each=True면 doc마다 watermark 전진 → 중단-재개."""
from __future__ import annotations

import json
import os
from pathlib import Path

import synapse_memory.wiki.ingest as ingest_mod
from synapse_memory.wiki.ingest import ingest_source
from synapse_memory.wiki.watermark import load_watermark


def _sess(root: Path, name: str, text: str, mtime: float) -> None:
    f = root / f"{name}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"message": {"role": "user", "content": text}}) + "\n", encoding="utf-8")
    os.utime(f, (mtime, mtime))


def test_checkpoint_advances_watermark_midway(tmp_path, monkeypatch) -> None:
    root = tmp_path / "raw" / "claude-code"
    _sess(root, "a", "first", 1_700_000_000)
    _sess(root, "b", "second", 1_700_000_100)
    state = tmp_path / "state.json"
    calls = {"n": 0}

    def flaky(prompt, *, system=None, model=None, json_schema=None, env=None, timeout=120, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("interrupted")
        return {"operations": [{"op": "create", "type": "concept",
                "slug": f"c{calls['n']}", "title": "C", "body": "b"}]}

    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", flaky)
    ingest_source("claude-code", vault_path=tmp_path, raw_root=root,
                  watermark_path=state, ai_env=None, today="2026-06-15", checkpoint_each=True)
    from datetime import datetime
    expected = datetime.fromtimestamp(1_700_000_000).isoformat(timespec="microseconds")
    assert load_watermark("claude-code", path=state) == expected


def test_without_checkpoint_saves_once_at_end(tmp_path, monkeypatch) -> None:
    root = tmp_path / "raw" / "claude-code"
    _sess(root, "a", "x", 1_700_000_000)
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured", lambda *a, **k: {"operations": []})
    ingest_source("claude-code", vault_path=tmp_path, raw_root=root,
                  watermark_path=state, ai_env=None, today="2026-06-15")
    assert load_watermark("claude-code", path=state) is not None
