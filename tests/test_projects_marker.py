"""Unit tests for synapse_memory.projects.marker (US1/US2 공통)."""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.projects.marker import (
    MARKER_END,
    MARKER_START,
    MarkerParseError,
    extract_block,
    inject_or_replace,
)


def test_inject_into_new_file(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    changed, prev = inject_or_replace(target, "## Synapse Memory\n\nProfile: /tmp/p.md\n")
    assert changed is True
    assert prev is None
    text = target.read_text(encoding="utf-8")
    assert MARKER_START in text
    assert MARKER_END in text
    assert "Profile: /tmp/p.md" in text


def test_append_to_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Existing instructions\n\nKeep this.\n", encoding="utf-8")

    inject_or_replace(target, "Synapse body\n")

    text = target.read_text(encoding="utf-8")
    assert "Keep this." in text, "기존 내용 보존"
    assert MARKER_START in text
    assert "Synapse body" in text
    assert text.index("Keep this.") < text.index(MARKER_START), "marker는 파일 끝에 append"


def test_replace_existing_marker_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text(
        f"top\n{MARKER_START}\nold body\n{MARKER_END}\nbottom\n",
        encoding="utf-8",
    )

    _changed, prev = inject_or_replace(target, "new body\n")

    text = target.read_text(encoding="utf-8")
    assert "new body" in text
    assert "old body" not in text
    assert "top" in text and "bottom" in text, "marker 바깥 보존"
    assert prev == "\nold body\n"


def test_byte_level_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    body = "Profile: /tmp/p.md\nPatterns: /tmp/d.md\n"
    inject_or_replace(target, body)
    snapshot = target.read_bytes()

    changed, _ = inject_or_replace(target, body)

    assert target.read_bytes() == snapshot, "동일 body 2회 호출 → 파일 동일"
    assert changed is False


def test_unclosed_marker_raises(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text(f"{MARKER_START}\nincomplete\n", encoding="utf-8")
    with pytest.raises(MarkerParseError):
        inject_or_replace(target, "anything")


def test_extract_block_returns_body(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text(
        f"top\n{MARKER_START}\nbody-line-1\nbody-line-2\n{MARKER_END}\nbottom\n",
        encoding="utf-8",
    )
    block = extract_block(target)
    assert block is not None
    assert "body-line-1" in block
    assert "body-line-2" in block
