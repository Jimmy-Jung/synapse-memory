"""Doctor fix whitelist 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.doctor import (
    DiagnosticStatus,
    diagnose_runtime_shim,
    planned_fix_actions,
)


def test_missing_runtime_shim_is_fixable_without_shell_mutation(tmp_path: Path) -> None:
    result = diagnose_runtime_shim(tmp_path / ".synapse" / "bin" / "synapse-memory")

    assert result.status == DiagnosticStatus.FAIL
    assert result.fixable is True
    assert result.fix_action_id == "recreate_runtime_shim"
    assert planned_fix_actions([result])[0].risk == "medium"
