"""Integration tests for `synapse-memory setup` / `sync` CLI (US1/US2/US3)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from synapse_memory.cli import main
from synapse_memory.projects.marker import MARKER_END, MARKER_START
from synapse_memory.projects.registry import load_registry


def _scaffold_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    ai = vault / "90_System" / "AI"
    ai.mkdir(parents=True)
    (ai / "Profile.md").write_text(
        "---\ntitle: AI Profile\n---\n# Profile\n\n- iOS 주력\n- Swift 아키텍처\n",
        encoding="utf-8",
    )
    (ai / "DecisionPatterns.md").write_text(
        "---\ntitle: Decision Patterns\n---\n# Patterns\n\n- 기능단위 커밋\n- 원인 분석 우선\n",
        encoding="utf-8",
    )
    return vault


def _setup_env(
    monkeypatch: pytest.MonkeyPatch, vault: Path, registry: Path, project: Path
) -> None:
    monkeypatch.setattr("synapse_memory.cli._setup_vault_path", lambda: vault)
    monkeypatch.setattr("synapse_memory.cli._setup_registry_path", lambda: registry)
    monkeypatch.chdir(project)


def test_setup_target_both_creates_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _scaffold_vault(tmp_path)
    project = tmp_path / "proj"
    project.mkdir()
    registry = tmp_path / "registry.yaml"
    _setup_env(monkeypatch, vault, registry, project)

    rc = main(["setup", "--target", "both"])

    assert rc == 0
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    claude = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert MARKER_START in agents and MARKER_END in agents
    assert MARKER_START in claude and MARKER_END in claude
    entries = load_registry(registry)
    assert len(entries) == 1
    assert entries[0].path == project.resolve()


def test_setup_idempotent_byte_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _scaffold_vault(tmp_path)
    project = tmp_path / "proj"
    project.mkdir()
    registry = tmp_path / "registry.yaml"
    _setup_env(monkeypatch, vault, registry, project)

    main(["setup", "--target", "agents"])
    agents_snapshot = (project / "AGENTS.md").read_bytes()

    main(["setup", "--target", "agents"])

    assert (project / "AGENTS.md").read_bytes() == agents_snapshot


def test_setup_dry_run_no_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _scaffold_vault(tmp_path)
    project = tmp_path / "proj"
    project.mkdir()
    registry = tmp_path / "registry.yaml"
    _setup_env(monkeypatch, vault, registry, project)

    rc = main(["setup", "--target", "both", "--dry-run"])

    assert rc == 0
    assert not (project / "AGENTS.md").exists()
    assert not (project / "CLAUDE.md").exists()
    assert not registry.exists()


def test_sync_updates_all_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _scaffold_vault(tmp_path)
    p1 = tmp_path / "p1"
    p1.mkdir()
    p2 = tmp_path / "p2"
    p2.mkdir()
    registry = tmp_path / "registry.yaml"

    _setup_env(monkeypatch, vault, registry, p1)
    main(["setup", "--target", "agents"])
    monkeypatch.chdir(p2)
    main(["setup", "--target", "agents"])

    profile = vault / "90_System" / "AI" / "Profile.md"
    profile.write_text(
        "---\ntitle: AI Profile\n---\n# Profile\n\n- 새 fact-line\n",
        encoding="utf-8",
    )

    rc = main(["sync"])

    assert rc == 0
    assert "새 fact-line" in (p1 / "AGENTS.md").read_text(encoding="utf-8")
    assert "새 fact-line" in (p2 / "AGENTS.md").read_text(encoding="utf-8")


def test_sync_marks_stale_when_project_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _scaffold_vault(tmp_path)
    project = tmp_path / "proj-gone"
    project.mkdir()
    registry = tmp_path / "registry.yaml"
    _setup_env(monkeypatch, vault, registry, project)

    main(["setup", "--target", "agents"])

    os.chdir(str(tmp_path))
    shutil.rmtree(project)

    rc = main(["sync"])

    assert rc == 0
    entries = load_registry(registry)
    assert any(e.state == "stale" for e in entries)
