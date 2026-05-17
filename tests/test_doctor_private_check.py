"""Unit tests for `diagnose_private_folder_deny` (US2)."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.doctor import (
    DiagnosticStatus,
    diagnose_private_folder_deny,
)


def test_ok_when_private_folder_absent(tmp_path: Path) -> None:
    result = diagnose_private_folder_deny(tmp_path)
    assert result.status == DiagnosticStatus.OK
    assert "Private 폴더" in result.message or "no private" in result.message.lower()


def test_warn_when_private_exists_but_no_settings(tmp_path: Path) -> None:
    (tmp_path / "90_System" / "Private").mkdir(parents=True)

    result = diagnose_private_folder_deny(tmp_path)

    assert result.status == DiagnosticStatus.WARN
    assert "settings.json" in result.message


def test_warn_when_deny_partially_missing(tmp_path: Path) -> None:
    (tmp_path / "90_System" / "Private").mkdir(parents=True)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings = settings_dir / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "permissions": {
                    "deny": [
                        "Read(./90_System/Private/**)",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = diagnose_private_folder_deny(tmp_path)

    assert result.status == DiagnosticStatus.WARN
    assert "Glob" in result.message or "Write" in result.message


def test_ok_when_all_three_deny_present(tmp_path: Path) -> None:
    (tmp_path / "90_System" / "Private").mkdir(parents=True)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings = settings_dir / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "permissions": {
                    "deny": [
                        "Read(./90_System/Private/**)",
                        "Glob(./90_System/Private/**)",
                        "Write(./90_System/Private/**)",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = diagnose_private_folder_deny(tmp_path)

    assert result.status == DiagnosticStatus.OK
