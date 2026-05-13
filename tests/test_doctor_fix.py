"""Doctor fix whitelist 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from synapse_memory.doctor import (
    DiagnosticStatus,
    apply_fix_actions,
    diagnose_private_permissions,
    diagnose_runtime_shim,
    planned_fix_actions,
)


def test_permission_drift_maps_to_whitelisted_fix(tmp_path: Path) -> None:
    private = tmp_path / ".synapse" / "private"
    private.mkdir(parents=True)
    os.chmod(private, 0o755)

    result = diagnose_private_permissions(private)

    assert result.status == DiagnosticStatus.FAIL
    assert result.fixable is True
    assert result.fix_action_id == "fix_private_permissions"


def test_apply_permission_fix_restores_0700(tmp_path: Path) -> None:
    private = tmp_path / ".synapse" / "private"
    private.mkdir(parents=True)
    os.chmod(private, 0o755)

    actions = planned_fix_actions([diagnose_private_permissions(private)])
    applied = apply_fix_actions(actions)

    assert applied[0].status == "success"
    assert stat.S_IMODE(private.stat().st_mode) == 0o700


def test_missing_runtime_shim_is_fixable_without_shell_mutation(tmp_path: Path) -> None:
    result = diagnose_runtime_shim(tmp_path / ".synapse" / "bin" / "synapse-memory")

    assert result.status == DiagnosticStatus.FAIL
    assert result.fixable is True
    assert result.fix_action_id == "recreate_runtime_shim"
    assert planned_fix_actions([result])[0].risk == "medium"
