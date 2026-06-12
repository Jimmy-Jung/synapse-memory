"""Claude Code/Codex hook install tests."""

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
    codex_hooks = tmp_path / ".codex" / "hooks.json"

    installed = install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)

    assert installed is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    hook = data["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == HOOK_COMMAND
    assert hook["timeout"] == 5

    codex_data = json.loads(codex_hooks.read_text(encoding="utf-8"))
    codex_group = codex_data["hooks"]["SessionStart"][0]
    codex_hook = codex_group["hooks"][0]
    assert codex_group["matcher"] == "startup|resume"
    assert codex_hook["type"] == "command"
    assert codex_hook["command"] == HOOK_COMMAND
    assert codex_hook["timeout"] == 5
    assert codex_hook["statusMessage"] == "Loading Synapse Memory context"


def test_install_session_hook_is_idempotent(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"

    assert install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks) is True
    before = settings.read_text(encoding="utf-8")
    codex_before = codex_hooks.read_text(encoding="utf-8")
    assert install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks) is False

    assert settings.read_text(encoding="utf-8") == before
    assert codex_hooks.read_text(encoding="utf-8") == codex_before


def test_diagnose_session_hook_reports_installed_and_missing(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"

    missing = diagnose_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)
    assert missing.installed is False
    assert "미설치" in missing.message
    assert "Claude Code" in missing.message
    assert "Codex" in missing.message

    install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)
    installed = diagnose_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)
    assert installed.installed is True
    assert "설치됨" in installed.message


def test_write_settings_uses_atomic_temp_cleanup(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"

    install_session_hook(settings_path=settings)

    assert json.loads(settings.read_text(encoding="utf-8"))
    assert not list(settings.parent.glob("settings-*.tmp"))


def test_uninstall_session_hook_removes_only_synapse_entry(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
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
    codex_hooks.parent.mkdir()
    codex_hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup|resume",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": HOOK_COMMAND,
                                    "timeout": 5,
                                }
                            ],
                        },
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "other-tool",
                                    "timeout": 1,
                                }
                            ],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    removed = uninstall_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)

    assert removed is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for group in data["hooks"]["SessionStart"]
        for hook in group.get("hooks", [])
    ]
    assert HOOK_COMMAND not in commands
    assert "other-tool" in commands

    codex_data = json.loads(codex_hooks.read_text(encoding="utf-8"))
    codex_commands = [
        hook["command"]
        for group in codex_data["hooks"]["SessionStart"]
        for hook in group.get("hooks", [])
    ]
    assert HOOK_COMMAND not in codex_commands
    assert "other-tool" in codex_commands
