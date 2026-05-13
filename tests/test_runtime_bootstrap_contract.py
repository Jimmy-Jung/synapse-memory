"""Runtime bootstrap 계약 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from synapse_memory.installer.runtime import (
    BootstrapPlan,
    build_synapse_shim,
    managed_bin_dir,
    render_bootstrap_script,
)
from synapse_memory.installer.state import load_manifest


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


def test_macos_installer_activates_claude_and_codex_plugins() -> None:
    script = Path("installer/SynapseMemory-Installer.command").read_text(encoding="utf-8")

    assert "activate_plugins()" in script
    assert "claude plugin marketplace add" in script
    assert "claude plugin install" in script
    assert "claude plugin enable" in script
    assert "codex plugin marketplace add" in script
    assert "install_codex_plugin_cache" in script
    assert "plugins/cache/${CODEX_MARKETPLACE_NAME}" in script
    assert 'plugins."{plugin_ref}"' in script
    assert "codex debug prompt-input" in script
    assert "sm:sm" in script
    assert "SYNAPSE_ACTIVATE_PLUGINS" in script


def test_codex_marketplace_catalog_points_to_plugin_manifest() -> None:
    marketplace = json.loads(Path(".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path(".codex-plugin/plugin.json").read_text(encoding="utf-8"))

    assert marketplace["name"] == "synapse-memory-marketplace"
    assert marketplace["interface"]["displayName"] == "Synapse Memory"

    plugins = marketplace["plugins"]
    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin["name"] == manifest["name"] == "sm"
    assert plugin["source"] == {"source": "local", "path": "./"}
    assert plugin["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert plugin["category"] == manifest["interface"]["category"]


def test_macos_installer_records_structured_state_manifest() -> None:
    script = Path("installer/SynapseMemory-Installer.command").read_text(encoding="utf-8")

    assert 'STATE_FILE="${LOG_DIR}/installer-${RUN_STAMP}.state.json"' in script
    assert "record_state_step()" in script
    assert "append_manifest_step" in script
    assert 'log_step "start" "success" "log=${LOG_FILE} state=${STATE_FILE}"' in script
    assert 'log_step "complete" "success" "dry_run=${DRY_RUN} state=${STATE_FILE}"' in script


def test_macos_installer_dry_run_smoke_writes_log_and_state_manifest(
    tmp_path: Path,
) -> None:
    repo_root = Path.cwd()
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_brew = fake_bin / "brew"
    fake_brew.write_text("#!/usr/bin/env sh\nexit 1\n", encoding="utf-8")
    fake_brew.chmod(0o755)

    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SYNAPSE_INSTALLER_DRY_RUN": "1",
        "SYNAPSE_INSTALLER_TEST_ARCH": "arm64",
        "SYNAPSE_INSTALLER_TEST_MODE": "1",
    }

    result = subprocess.run(
        ["zsh", "installer/SynapseMemory-Installer.command"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    log_dir = home / "Library" / "Logs" / "SynapseMemory"
    log_files = sorted(log_dir.glob("installer-*.log"))
    state_files = sorted(log_dir.glob("installer-*.state.json"))

    assert result.returncode == 0, result.stderr
    assert len(log_files) == 1
    assert len(state_files) == 1
    assert "bootstrap_runtime preview" in log_files[0].read_text(encoding="utf-8")

    manifest = load_manifest(state_files[0])
    assert manifest is not None
    assert manifest.state == "succeeded"
    assert manifest.dry_run is True
    assert manifest.log_path == str(log_files[0])
    assert manifest.state_path == str(state_files[0])

    steps = {step.step_id: step for step in manifest.steps}
    assert steps["start"].phase == "lifecycle"
    assert steps["consent"].status == "success"
    assert steps["platform"].status == "success"
    assert steps["bootstrap_runtime"].status == "preview"
    assert steps["activate_claude_plugin"].status == "preview"
    assert steps["activate_codex_plugin"].status == "preview"
    assert steps["complete"].status == "success"
