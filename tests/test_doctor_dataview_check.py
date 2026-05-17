"""Unit tests for diagnose_dataview_plugin (US3 of 015-graph-viz)."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.doctor import (
    DiagnosticStatus,
    diagnose_dataview_plugin,
)


def test_dataview_ok_when_installed(tmp_path: Path) -> None:
    obsidian = tmp_path / ".obsidian"
    obsidian.mkdir()
    (obsidian / "community-plugins.json").write_text(
        json.dumps(["dataview", "templater-obsidian"]),
        encoding="utf-8",
    )
    result = diagnose_dataview_plugin(tmp_path)
    assert result.status == DiagnosticStatus.OK


def test_dataview_warn_when_not_in_plugins(tmp_path: Path) -> None:
    obsidian = tmp_path / ".obsidian"
    obsidian.mkdir()
    (obsidian / "community-plugins.json").write_text(
        json.dumps(["templater-obsidian"]),
        encoding="utf-8",
    )
    result = diagnose_dataview_plugin(tmp_path)
    assert result.status == DiagnosticStatus.WARN
    assert "dataview" in result.message.lower()


def test_dataview_warn_when_obsidian_folder_missing(tmp_path: Path) -> None:
    result = diagnose_dataview_plugin(tmp_path)
    assert result.status == DiagnosticStatus.WARN
    assert ".obsidian" in result.message or "obsidian" in result.message.lower()
