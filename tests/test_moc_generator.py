"""Unit tests for synapse_memory.moc (US2 of 015-graph-viz)."""

from __future__ import annotations

from pathlib import Path

from synapse_memory.moc import (
    MOC_MARKER_END,
    MOC_MARKER_START,
    generate_moc_body,
    write_or_update_moc,
)


def _scaffold_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "20_Reference" / "Projects").mkdir(parents=True)
    (vault / "20_Reference" / "Companies").mkdir(parents=True)
    (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)
    (vault / "90_System" / "AI" / "DailyReports").mkdir(parents=True)
    return vault


def test_moc_creates_new_with_dataview_blocks(tmp_path: Path) -> None:
    vault = _scaffold_vault(tmp_path)

    moc_path = write_or_update_moc(vault)

    assert moc_path.is_file()
    text = moc_path.read_text(encoding="utf-8")
    assert MOC_MARKER_START in text
    assert MOC_MARKER_END in text
    assert "```dataview" in text
    assert "Projects" in text or "20_Reference/Projects" in text
    assert "DailyReports" in text or "DailyReport" in text


def test_moc_idempotent_user_content_preserved(tmp_path: Path) -> None:
    vault = _scaffold_vault(tmp_path)
    moc = vault / "90_System" / "AI" / "MOC.md"
    moc.parent.mkdir(parents=True, exist_ok=True)
    moc.write_text(
        "# My MOC\n\n사용자 자유 메모입니다.\n\n"
        f"{MOC_MARKER_START}\n(old auto block)\n{MOC_MARKER_END}\n\n"
        "## 사용자 끝 섹션\n",
        encoding="utf-8",
    )

    write_or_update_moc(vault)

    text = moc.read_text(encoding="utf-8")
    assert "사용자 자유 메모입니다." in text, "marker 위 사용자 영역 보존"
    assert "사용자 끝 섹션" in text, "marker 아래 사용자 영역 보존"
    assert "(old auto block)" not in text, "marker 사이 sm 영역은 교체"


def test_moc_marker_replace_does_not_break_outside(tmp_path: Path) -> None:
    vault = _scaffold_vault(tmp_path)
    moc = vault / "90_System" / "AI" / "MOC.md"
    moc.parent.mkdir(parents=True, exist_ok=True)
    head = "# header\n\n"
    tail = "\n## tail\n사용자 추가\n"
    moc.write_text(
        f"{head}{MOC_MARKER_START}\nfirst\n{MOC_MARKER_END}{tail}",
        encoding="utf-8",
    )

    write_or_update_moc(vault)
    snapshot = moc.read_text(encoding="utf-8")

    write_or_update_moc(vault)
    assert moc.read_text(encoding="utf-8") == snapshot


def test_generate_moc_body_returns_markdown(tmp_path: Path) -> None:
    vault = _scaffold_vault(tmp_path)
    body = generate_moc_body(vault)
    assert "```dataview" in body
    assert "Projects" in body or "20_Reference/Projects" in body
