"""구조화된 doctor 진단 및 whitelist repair.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DiagnosticStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DiagnosticResult:
    check_id: str
    status: DiagnosticStatus
    message: str
    fixable: bool = False
    fix_action_id: str | None = None
    target: Path | None = None


@dataclass(frozen=True)
class FixResult:
    action_id: str
    status: str
    summary: str


@dataclass(frozen=True)
class FixAction:
    id: str
    description: str
    risk: str
    apply: Callable[[], FixResult]


def diagnose_private_permissions(private_root: Path) -> DiagnosticResult:
    root = private_root.expanduser()
    if not root.exists():
        return DiagnosticResult(
            check_id="private_permissions",
            status=DiagnosticStatus.FAIL,
            message=f"{root} 없음",
            fixable=True,
            fix_action_id="fix_private_permissions",
            target=root,
        )
    mode = stat.S_IMODE(root.stat().st_mode)
    if mode != 0o700:
        return DiagnosticResult(
            check_id="private_permissions",
            status=DiagnosticStatus.FAIL,
            message=f"{root} 권한이 0{mode:o}입니다. 0700이 필요합니다.",
            fixable=True,
            fix_action_id="fix_private_permissions",
            target=root,
        )
    return DiagnosticResult(
        check_id="private_permissions",
        status=DiagnosticStatus.OK,
        message=f"{root} 권한 정상",
        target=root,
    )


def diagnose_runtime_shim(shim_path: Path) -> DiagnosticResult:
    path = shim_path.expanduser()
    if not path.is_file():
        return DiagnosticResult(
            check_id="runtime_shim",
            status=DiagnosticStatus.FAIL,
            message=f"{path} command shim 없음",
            fixable=True,
            fix_action_id="recreate_runtime_shim",
            target=path,
        )
    if not os.access(path, os.X_OK):
        return DiagnosticResult(
            check_id="runtime_shim",
            status=DiagnosticStatus.FAIL,
            message=f"{path} 실행 권한 없음",
            fixable=True,
            fix_action_id="recreate_runtime_shim",
            target=path,
        )
    return DiagnosticResult(
        check_id="runtime_shim",
        status=DiagnosticStatus.OK,
        message=f"{path} command shim 정상",
        target=path,
    )


def planned_fix_actions(results: list[DiagnosticResult]) -> list[FixAction]:
    actions: list[FixAction] = []
    for result in results:
        if not result.fixable or result.fix_action_id is None:
            continue
        if result.fix_action_id == "fix_private_permissions" and result.target is not None:
            target = result.target
            actions.append(
                FixAction(
                    id="fix_private_permissions",
                    description=f"{target} 권한을 0700으로 복구",
                    risk="low",
                    apply=_make_private_permission_fix(target),
                )
            )
        elif result.fix_action_id == "recreate_runtime_shim" and result.target is not None:
            target = result.target
            actions.append(
                FixAction(
                    id="recreate_runtime_shim",
                    description=f"{target} command shim 재생성 안내",
                    risk="medium",
                    apply=_make_runtime_guidance_fix(target),
                )
            )
    return actions


def apply_fix_actions(actions: list[FixAction]) -> list[FixResult]:
    return [action.apply() for action in actions]


def _fix_private_permissions(target: Path) -> FixResult:
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    return FixResult(
        action_id="fix_private_permissions",
        status="success",
        summary=f"{target} 권한을 0700으로 복구",
    )


def _make_private_permission_fix(target: Path) -> Callable[[], FixResult]:
    def apply() -> FixResult:
        return _fix_private_permissions(target)

    return apply


def _runtime_rerun_guidance(target: Path) -> FixResult:
    return FixResult(
        action_id="recreate_runtime_shim",
        status="manual_required",
        summary=f"{target} 재생성은 installer 또는 scripts/bootstrap_runtime.sh 재실행 필요",
    )


def _make_runtime_guidance_fix(target: Path) -> Callable[[], FixResult]:
    def apply() -> FixResult:
        return _runtime_rerun_guidance(target)

    return apply
