"""Raw RAG chunker tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.rag.chunker import (
    RawChunk,
    chunk_text,
    discover_raw_sources,
    raw_chunks_from_file,
    tokenize_text,
)


def test_tokenize_text_preserves_korean_english_numbers() -> None:
    assert tokenize_text("당근마켓 iOS 2026 회고") == ["당근마켓", "iOS", "2026", "회고"]


def test_chunk_text_uses_deterministic_overlap() -> None:
    text = " ".join(f"w{i}" for i in range(10))

    chunks = chunk_text(text, max_tokens=4, overlap=1)

    assert chunks == [
        "w0 w1 w2 w3",
        "w3 w4 w5 w6",
        "w6 w7 w8 w9",
    ]


def test_chunk_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", max_tokens=3, overlap=3)


def test_discover_raw_sources_finds_active_and_redacted_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    active = vault / "10_Active"
    active.mkdir(parents=True)
    (active / "raw-note.md").write_text("당근마켓 메모", encoding="utf-8")
    (vault / "90_System").mkdir()
    (vault / "90_System" / "ignored.md").write_text("ignore", encoding="utf-8")

    l0_root = tmp_path / "private"
    claude_dir = l0_root / "redacted" / "claude-code"
    claude_dir.mkdir(parents=True)
    (claude_dir / "session.jsonl").write_text('{"text":"redacted"}', encoding="utf-8")
    monkeypatch.setenv("SYNAPSE_L0_ROOT", str(l0_root))

    sources = discover_raw_sources(vault_path=vault)

    assert [s.source_kind for s in sources] == ["raw_obsidian", "raw_claude_code"]
    assert sources[0].path == active / "raw-note.md"
    assert sources[1].path == claude_dir / "session.jsonl"


def test_raw_chunks_from_file_builds_stable_redacted_metadata(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "10_Active" / "memo.md"
    note.parent.mkdir(parents=True)
    note.write_text("email user@example.com 당근마켓", encoding="utf-8")

    chunks = raw_chunks_from_file(
        note,
        source_kind="raw_obsidian",
        root_path=vault,
        redact=lambda text: text.replace("user@example.com", "[EMAIL_1]"),
        max_tokens=10,
    )

    assert chunks == [
        RawChunk(
            id=chunks[0].id,
            source_kind="raw_obsidian",
            path="10_Active/memo.md",
            chunk_index=0,
            text="email [EMAIL_1] 당근마켓",
            created=chunks[0].created,
            display_name="memo.md",
        )
    ]
    assert chunks[0].id.startswith("raw_obsidian:")
    assert "user@example.com" not in chunks[0].text
