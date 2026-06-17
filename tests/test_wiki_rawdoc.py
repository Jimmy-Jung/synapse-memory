# tests/test_wiki_rawdoc.py
"""claude-code 미러 jsonl → RawDoc."""
from __future__ import annotations

import json
import os
from pathlib import Path

from synapse_memory.wiki.rawdoc import RawDoc, iter_new_raw


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events),
        encoding="utf-8",
    )


def test_extracts_text_from_message_events(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    f = root / "projects" / "demo" / "sess1.jsonl"
    _write_jsonl(
        f,
        [
            {"type": "user", "message": {"role": "user", "content": "프로젝트 구조 알려줘"}},
            {"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "text", "text": "MVVM 입니다"}]}},
        ],
    )
    docs = list(iter_new_raw("claude-code", since=None, root=root))
    assert len(docs) == 1
    assert isinstance(docs[0], RawDoc)
    assert "프로젝트 구조 알려줘" in docs[0].text
    assert "MVVM 입니다" in docs[0].text
    assert docs[0].ref == "claude-code:projects/demo/sess1.jsonl"


def test_since_filters_older_files(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    old = root / "old.jsonl"
    new = root / "new.jsonl"
    _write_jsonl(old, [{"message": {"role": "user", "content": "old"}}])
    _write_jsonl(new, [{"message": {"role": "user", "content": "new"}}])
    os.utime(old, (1_000_000_000, 1_000_000_000))
    os.utime(new, (2_000_000_000, 2_000_000_000))
    docs = list(iter_new_raw("claude-code", since="2020-01-01T00:00:00", root=root))
    texts = [d.text for d in docs]
    assert "new" in texts and "old" not in texts


def test_missing_root_returns_empty(tmp_path: Path) -> None:
    assert list(iter_new_raw("claude-code", since=None, root=tmp_path / "nope")) == []


def test_skips_unparseable_lines(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    f = root / "s.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('{"message":{"role":"user","content":"ok"}}\nGARBAGE\n', encoding="utf-8")
    docs = list(iter_new_raw("claude-code", since=None, root=root))
    assert len(docs) == 1
    assert "ok" in docs[0].text
