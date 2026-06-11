"""Claude Code hook install tests."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.hooks.install import (
    HOOK_COMMAND,
    diagnose_session_hook,
    install_session_hook,
    uninstall_session_hook,
)


def test_install_session_hook_creates_settings_entry(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"

    installed = install_session_hook(settings_path=settings)

    assert installed is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    hook = data["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == HOOK_COMMAND
    assert hook["timeout"] == 5


def test_install_session_hook_is_idempotent(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"

    assert install_session_hook(settings_path=settings) is True
    before = settings.read_text(encoding="utf-8")
    assert install_session_hook(settings_path=settings) is False

    assert settings.read_text(encoding="utf-8") == before


def test_diagnose_session_hook_reports_installed_and_missing(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"

    missing = diagnose_session_hook(settings_path=settings)
    assert missing.installed is False
    assert "미설치" in missing.message

    install_session_hook(settings_path=settings)
    installed = diagnose_session_hook(settings_path=settings)
    assert installed.installed is True
    assert "설치됨" in installed.message


def test_write_settings_uses_atomic_temp_cleanup(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"

    install_session_hook(settings_path=settings)

    assert json.loads(settings.read_text(encoding="utf-8"))
    assert not list(settings.parent.glob("settings-*.tmp"))


def test_uninstall_session_hook_removes_only_synapse_entry(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 5}]},
                        {"hooks": [{"type": "command", "command": "other-tool", "timeout": 1}]},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    removed = uninstall_session_hook(settings_path=settings)

    assert removed is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for group in data["hooks"]["SessionStart"]
        for hook in group.get("hooks", [])
    ]
    assert HOOK_COMMAND not in commands
    assert "other-tool" in commands
