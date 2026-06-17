"""min_age_seconds: 최근 변경된(진행 중) 파일은 건너뛴다."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from synapse_memory.wiki.rawdoc import iter_new_raw


def _sess(root: Path, name: str, text: str) -> Path:
    f = root / f"{name}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"message": {"role": "user", "content": text}}) + "\n", encoding="utf-8")
    return f


def test_recent_file_skipped_when_min_age_set(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    recent = _sess(root, "recent", "진행 중")
    settled = _sess(root, "settled", "끝난 대화")
    now = time.time()
    os.utime(recent, (now, now))
    os.utime(settled, (now - 600, now - 600))
    docs = list(iter_new_raw("claude-code", since=None, root=root, min_age_seconds=180, now=now))
    texts = [d.text for d in docs]
    assert "끝난 대화" in texts and "진행 중" not in texts


def test_no_min_age_returns_all(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    _sess(root, "a", "x")
    assert len(list(iter_new_raw("claude-code", since=None, root=root))) == 1
