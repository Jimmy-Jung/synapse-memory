"""Runtime bootstrap 계약 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.installer.runtime import (
    BootstrapPlan,
    build_synapse_shim,
    managed_bin_dir,
    render_bootstrap_script,
)


def test_managed_bin_dir_uses_synapse_home(tmp_path: Path) -> None:
    assert managed_bin_dir(home=tmp_path) == tmp_path / ".synapse" / "bin"


def test_synapse_shim_does_not_call_system_python() -> None:
    content = build_synapse_shim(
        project_source="/tmp/synapse-memory",
        executable="synapse-memory",
    )

    assert "/usr/bin/python3" not in content
    assert "python3 " not in content
    assert "uv tool run" in content
    assert "synapse-memory" in content


def test_bootstrap_script_preserves_canonical_command() -> None:
    script = render_bootstrap_script(
        BootstrapPlan(project_source="/tmp/synapse-memory", expose_synapse_alias=True)
    )

    assert "synapse-memory" in script
    assert "ln -sf" in script
    assert "/usr/bin/python3" not in script


def test_macos_installer_does_not_assign_zsh_status_reserved_variable() -> None:
    script = Path("installer/SynapseMemory-Installer.command").read_text(encoding="utf-8")

    assert "local status=" not in script
    assert "local step_status=" in script


def test_macos_installer_skips_existing_obsidian_app_bundle() -> None:
    script = Path("installer/SynapseMemory-Installer.command").read_text(encoding="utf-8")

    assert "obsidian_bundle_is_valid()" in script
    assert 'bundle_id}" = "md.obsidian"' in script
    assert "source=/Applications/Obsidian.app" in script
    assert "--adopt obsidian" not in script


def test_macos_installer_detects_existing_claude_cli_before_cask_install() -> None:
    script = Path("installer/SynapseMemory-Installer.command").read_text(encoding="utf-8")

    assert "command -v claude" in script
    assert "path=$(command -v claude)" in script
    assert "brew install --cask claude-code" in script
