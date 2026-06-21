"""Claude Code/Codex hook install tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from synapse_memory.hooks.install import (
    HOOK_COMMAND,
    diagnose_session_hook,
    install_session_hook,
    uninstall_session_hook,
)


def test_install_session_hook_creates_settings_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
    command = "/opt/synapse/bin/synapse-memory hook run --event session-start"
    monkeypatch.setattr(
        "synapse_memory.hooks.install._resolve_hook_executable",
        lambda: "/opt/synapse/bin/synapse-memory",
    )

    installed = install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)

    assert installed is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    hook = data["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == command
    assert hook["timeout"] == 5

    codex_data = json.loads(codex_hooks.read_text(encoding="utf-8"))
    codex_group = codex_data["hooks"]["SessionStart"][0]
    codex_hook = codex_group["hooks"][0]
    assert codex_group["matcher"] == "startup|resume"
    assert codex_hook["type"] == "command"
    assert codex_hook["command"] == command
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


def test_install_session_hook_normalizes_legacy_path_dependent_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
    settings.parent.mkdir()
    codex_hooks.parent.mkdir()
    settings.write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": HOOK_COMMAND}]}]}}),
        encoding="utf-8",
    )
    codex_hooks.write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": HOOK_COMMAND}]}]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "synapse_memory.hooks.install._resolve_hook_executable",
        lambda: "/Users/jimmy/.local/bin/synapse-memory",
    )

    changed = install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)

    assert changed is True
    assert (
        json.loads(settings.read_text(encoding="utf-8"))["hooks"]["SessionStart"][0]
        ["hooks"][0]["command"]
        == "/Users/jimmy/.local/bin/synapse-memory hook run --event session-start"
    )
    assert (
        json.loads(codex_hooks.read_text(encoding="utf-8"))["hooks"]["SessionStart"][0]
        ["hooks"][0]["command"]
        == "/Users/jimmy/.local/bin/synapse-memory hook run --event session-start"
    )


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


def test_diagnose_session_hook_reports_ready_for_registered_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    executable = tmp_path / "bin" / "synapse-memory"
    project.mkdir()
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(executable, 0o755)
    (home / "context").mkdir(parents=True)
    (home / "context" / "rendered.md").write_text("context", encoding="utf-8")
    (home / "projects.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "path": str(project),
                        "target": "hook",
                        "registered_at": "2026-06-21",
                        "state": "active",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "synapse_memory.hooks.install._resolve_hook_executable",
        lambda: str(executable),
    )
    install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)

    diagnostic = diagnose_session_hook(
        settings_path=settings,
        codex_hooks_path=codex_hooks,
        cwd=project,
        synapse_home=home,
    )

    assert diagnostic.installed is True
    assert diagnostic.ready is True
    assert diagnostic.project_registered is True
    assert diagnostic.cache_available is True
    assert diagnostic.command_stable is True


def test_diagnose_session_hook_warns_when_current_project_unregistered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    executable = tmp_path / "bin" / "synapse-memory"
    project.mkdir()
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(executable, 0o755)
    (home / "context").mkdir(parents=True)
    (home / "context" / "rendered.md").write_text("context", encoding="utf-8")
    (home / "projects.json").write_text('{"projects": []}', encoding="utf-8")
    monkeypatch.setattr(
        "synapse_memory.hooks.install._resolve_hook_executable",
        lambda: str(executable),
    )
    install_session_hook(settings_path=settings, codex_hooks_path=codex_hooks)

    diagnostic = diagnose_session_hook(
        settings_path=settings,
        codex_hooks_path=codex_hooks,
        cwd=project,
        synapse_home=home,
    )

    assert diagnostic.installed is True
    assert diagnostic.ready is False
    assert diagnostic.project_registered is False
    assert "현재 프로젝트 미등록" in diagnostic.message


def test_diagnose_session_hook_warns_for_path_dependent_legacy_command(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    project.mkdir()
    (home / "context").mkdir(parents=True)
    (home / "context" / "rendered.md").write_text("context", encoding="utf-8")
    (home / "projects.json").write_text(
        json.dumps({"projects": [{"path": str(project), "state": "active"}]}),
        encoding="utf-8",
    )
    settings.parent.mkdir()
    codex_hooks.parent.mkdir()
    payload = {"hooks": {"SessionStart": [{"hooks": [{"command": HOOK_COMMAND}]}]}}
    settings.write_text(json.dumps(payload), encoding="utf-8")
    codex_hooks.write_text(json.dumps(payload), encoding="utf-8")

    diagnostic = diagnose_session_hook(
        settings_path=settings,
        codex_hooks_path=codex_hooks,
        cwd=project,
        synapse_home=home,
    )

    assert diagnostic.installed is True
    assert diagnostic.ready is False
    assert diagnostic.command_stable is False
    assert "PATH 의존" in diagnostic.message


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
