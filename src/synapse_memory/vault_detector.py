"""Obsidian vault 감지.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class VaultSource(StrEnum):
    OBSIDIAN_APP_CONFIG = "obsidian_app_config"
    ICLOUD_OBSIDIAN = "icloud_obsidian"
    DOCUMENTS_OBSIDIAN = "documents_obsidian"
    CONVENTIONAL = "conventional"
    EXISTING_CONFIG = "existing_config"
    CREATED_DEFAULT = "created_default"


@dataclass(frozen=True)
class VaultCandidate:
    path: Path
    source: VaultSource
    display_name: str
    has_obsidian_dir: bool
    confidence: int
    needs_creation: bool = False
    is_recommended: bool = False


def icloud_obsidian_root(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return root / "Library/Mobile Documents/iCloud~md~obsidian/Documents"


def documents_default_vault_path(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return (root / "Documents" / "SynapseVault").resolve()


def obsidian_app_config_path(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return root / "Library/Application Support/obsidian/obsidian.json"


def obsidian_app_config_vault_paths(*, home: Path | None = None) -> list[Path]:
    config_path = obsidian_app_config_path(home=home)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    vaults = payload.get("vaults")
    if not isinstance(vaults, dict):
        return []

    paths: list[Path] = []
    for value in vaults.values():
        if not isinstance(value, dict):
            continue
        raw_path = value.get("path")
        if isinstance(raw_path, str) and raw_path.strip():
            paths.append(Path(raw_path).expanduser())
    return paths


def default_vault_path(*, home: Path | None = None) -> VaultCandidate:
    root = (home or Path.home()).expanduser()
    icloud_root = icloud_obsidian_root(home=root)
    if icloud_root.is_dir():
        path = (icloud_root / "SynapseVault").resolve()
        display_name = "추천: iCloud SynapseVault 새로 만들기"
        confidence = 50
    else:
        path = documents_default_vault_path(home=root)
        display_name = "SynapseVault 새로 만들기"
        confidence = 10
    return VaultCandidate(
        path=path,
        source=VaultSource.CREATED_DEFAULT,
        display_name=display_name,
        has_obsidian_dir=False,
        confidence=confidence,
        needs_creation=True,
        is_recommended=True,
    )


def creation_vault_candidates(*, home: Path | None = None) -> list[VaultCandidate]:
    root = (home or Path.home()).expanduser()
    candidates = [default_vault_path(home=root)]
    local_path = documents_default_vault_path(home=root)
    if candidates[0].path != local_path:
        candidates.append(
            VaultCandidate(
                path=local_path,
                source=VaultSource.CREATED_DEFAULT,
                display_name="로컬 Documents SynapseVault 새로 만들기",
                has_obsidian_dir=False,
                confidence=10,
                needs_creation=True,
                is_recommended=False,
            )
        )
    return candidates


def detect_vault_candidates(
    *,
    home: Path | None = None,
    existing_config: Path | None = None,
) -> list[VaultCandidate]:
    root = (home or Path.home()).expanduser()
    candidates: list[VaultCandidate] = []
    seen: set[Path] = set()

    def add(path: Path, source: VaultSource, confidence: int) -> None:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            return
        obsidian_dir = resolved / ".obsidian"
        if not obsidian_dir.is_dir():
            return
        seen.add(resolved)
        candidates.append(
            VaultCandidate(
                path=resolved,
                source=source,
                display_name=resolved.name,
                has_obsidian_dir=True,
                confidence=confidence,
            )
        )

    if existing_config is not None:
        add(existing_config, VaultSource.EXISTING_CONFIG, 100)

    for path in obsidian_app_config_vault_paths(home=root):
        add(path, VaultSource.OBSIDIAN_APP_CONFIG, 95)

    icloud_root = icloud_obsidian_root(home=root)
    if icloud_root.is_dir():
        for path in sorted(icloud_root.iterdir()):
            if path.is_dir():
                add(path, VaultSource.ICLOUD_OBSIDIAN, 90)

    documents = root / "Documents"
    if documents.is_dir():
        for path in sorted(documents.iterdir()):
            if path.is_dir():
                add(path, VaultSource.DOCUMENTS_OBSIDIAN, 70)

    for path in (root / "Obsidian", root / "Documents" / "Obsidian"):
        add(path, VaultSource.CONVENTIONAL, 60)

    if candidates:
        return sorted(candidates, key=lambda item: (-item.confidence, item.path.as_posix()))
    return [default_vault_path(home=root)]


def installer_vault_choices(
    *,
    home: Path | None = None,
    existing_config: Path | None = None,
) -> list[VaultCandidate]:
    """GUI installer에 표시할 기존 vault + 새 vault 생성 후보."""
    existing = [
        candidate
        for candidate in detect_vault_candidates(
            home=home,
            existing_config=existing_config,
        )
        if not candidate.needs_creation
    ]
    seen = {candidate.path for candidate in existing}
    creation = [
        candidate
        for candidate in creation_vault_candidates(home=home)
        if candidate.path not in seen
    ]
    return [*existing, *creation]


def select_default_candidate(candidates: list[VaultCandidate]) -> VaultCandidate | None:
    real_candidates = [candidate for candidate in candidates if not candidate.needs_creation]
    if len(real_candidates) == 1:
        return real_candidates[0]
    if not real_candidates and len(candidates) == 1:
        return candidates[0]
    return None
