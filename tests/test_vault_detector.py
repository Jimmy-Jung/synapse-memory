"""Obsidian vault 감지 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.vault_detector import (
    VaultSource,
    creation_vault_candidates,
    default_vault_path,
    detect_vault_candidates,
    installer_vault_choices,
    select_default_candidate,
)


def _vault(path: Path) -> Path:
    (path / ".obsidian").mkdir(parents=True)
    return path


def test_detects_existing_config_before_other_candidates(tmp_path: Path) -> None:
    home = tmp_path / "home"
    configured = _vault(tmp_path / "configured")
    _vault(home / "Documents" / "Work")

    candidates = detect_vault_candidates(home=home, existing_config=configured)

    assert candidates[0].path == configured.resolve()
    assert candidates[0].source == VaultSource.EXISTING_CONFIG


def test_detects_icloud_and_documents_vaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    icloud = _vault(home / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Main")
    docs = _vault(home / "Documents" / "Research")

    candidates = detect_vault_candidates(home=home)
    paths = [candidate.path for candidate in candidates]

    assert icloud.resolve() in paths
    assert docs.resolve() in paths
    assert candidates[0].source == VaultSource.ICLOUD_OBSIDIAN


def test_returns_default_creation_candidate_when_no_vault_exists(tmp_path: Path) -> None:
    home = tmp_path / "home"

    candidates = detect_vault_candidates(home=home)

    assert candidates == [default_vault_path(home=home)]
    assert candidates[0].needs_creation is True
    assert candidates[0].source == VaultSource.CREATED_DEFAULT


def test_default_creation_candidate_prefers_icloud_container(tmp_path: Path) -> None:
    home = tmp_path / "home"
    icloud_root = home / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
    icloud_root.mkdir(parents=True)

    candidate = default_vault_path(home=home)

    assert candidate.path == (icloud_root / "SynapseVault").resolve()
    assert candidate.is_recommended is True
    assert "iCloud" in candidate.display_name


def test_creation_candidates_include_icloud_recommendation_and_local_option(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    icloud_root = home / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
    icloud_root.mkdir(parents=True)

    candidates = creation_vault_candidates(home=home)

    assert candidates[0].path == (icloud_root / "SynapseVault").resolve()
    assert candidates[0].is_recommended is True
    assert candidates[1].path == (home / "Documents" / "SynapseVault").resolve()
    assert candidates[1].is_recommended is False


def test_select_default_candidate_requires_gui_when_multiple_real_vaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _vault(home / "Documents" / "A")
    _vault(home / "Documents" / "B")

    candidates = detect_vault_candidates(home=home)

    assert select_default_candidate(candidates) is None


def test_installer_choices_include_existing_vaults_and_creation_options(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    existing = _vault(home / "Documents" / "Work")
    icloud_root = home / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
    icloud_root.mkdir(parents=True)

    choices = installer_vault_choices(home=home)
    paths = [choice.path for choice in choices]

    assert existing.resolve() in paths
    assert (icloud_root / "SynapseVault").resolve() in paths
    assert (home / "Documents" / "SynapseVault").resolve() in paths
