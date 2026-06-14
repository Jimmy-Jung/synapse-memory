# tests/test_wiki_watermark.py
"""ingest watermark load/save."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.watermark import load_watermark, save_watermark


def test_load_missing_returns_none(tmp_path: Path) -> None:
    assert load_watermark("claude-code", path=tmp_path / "state.json") is None


def test_save_then_load(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    save_watermark("claude-code", "2026-06-14T10:00:00", path=p)
    assert load_watermark("claude-code", path=p) == "2026-06-14T10:00:00"


def test_save_is_per_source(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    save_watermark("claude-code", "2026-06-14T10:00:00", path=p)
    save_watermark("obsidian", "2026-06-13T09:00:00", path=p)
    assert load_watermark("claude-code", path=p) == "2026-06-14T10:00:00"
    assert load_watermark("obsidian", path=p) == "2026-06-13T09:00:00"


def test_corrupt_file_treated_as_empty(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text("not json", encoding="utf-8")
    assert load_watermark("claude-code", path=p) is None
