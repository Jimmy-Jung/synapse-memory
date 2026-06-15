# tests/test_wiki_log.py
"""log.md append (시간순, grep 친화)."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.log import append_log, log_path


def test_log_path_is_vault_root(tmp_path: Path) -> None:
    assert log_path(vault_path=tmp_path) == tmp_path / "log.md"


def test_append_creates_and_appends(tmp_path: Path) -> None:
    append_log("ingest claude-code: 2 pages (synapse-memory, rag)",
               vault_path=tmp_path, when="2026-06-14T10:00:00")
    append_log("ingest claude-code: 1 page (acme)",
               vault_path=tmp_path, when="2026-06-14T11:00:00")
    text = (tmp_path / "log.md").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2
    assert "2026-06-14T10:00:00" in lines[0]
    assert "synapse-memory" in lines[0]
    assert "acme" in lines[1]
