"""구조화된 doctor 진단 및 whitelist repair.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import json
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


_PRIVATE_FOLDER_DENY_REQUIRED = (
    "Read(./90_System/Private/**)",
    "Glob(./90_System/Private/**)",
    "Write(./90_System/Private/**)",
)


def diagnose_private_folder_deny(vault: Path) -> DiagnosticResult:
    """vault `90_System/Private/`가 있으면 `.claude/settings.json`의 permissions.deny 검사."""
    vault_root = vault.expanduser()
    private = vault_root / "90_System" / "Private"
    if not private.is_dir():
        return DiagnosticResult(
            check_id="private_folder_deny",
            status=DiagnosticStatus.OK,
            message="vault에 Private 폴더 없음 — 추가 차단 설정 불필요",
            target=private,
        )

    settings = vault_root / ".claude" / "settings.json"
    if not settings.is_file():
        return DiagnosticResult(
            check_id="private_folder_deny",
            status=DiagnosticStatus.WARN,
            message=(
                f"Private 폴더 있음, 그러나 {settings} 없음. "
                "permissions.deny로 Read/Glob/Write 셋 다 차단 필요."
            ),
            target=settings,
        )

    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DiagnosticResult(
            check_id="private_folder_deny",
            status=DiagnosticStatus.FAIL,
            message=f"{settings} 파싱 실패: {exc}",
            target=settings,
        )

    deny = set(data.get("permissions", {}).get("deny", []))
    missing = [rule for rule in _PRIVATE_FOLDER_DENY_REQUIRED if rule not in deny]
    if missing:
        return DiagnosticResult(
            check_id="private_folder_deny",
            status=DiagnosticStatus.WARN,
            message="permissions.deny에 누락된 항목: " + ", ".join(missing),
            target=settings,
        )

    return DiagnosticResult(
        check_id="private_folder_deny",
        status=DiagnosticStatus.OK,
        message="Private 폴더 차단 정상 (Read/Glob/Write 셋 다 deny)",
        target=settings,
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


def diagnose_vault_config_consistency(
    config_vault: str | None,
    *,
    home: Path | None = None,
) -> DiagnosticResult:
    """config.yaml vault 경로와 vault detection 결과의 일관성 점검.

    silent overwrite 위험 (사용자 의도 덮어쓰기) 회피를 위해
    fix_action_id 는 `set_config_vault` 이며, planned_fix_actions 에는
    포함되지 않는다. 적용은 `synapse-memory doctor --fix-config` 로만 가능.
    """
    from synapse_memory.vault_detector import detect_vault_candidates

    detected = detect_vault_candidates(home=home)
    real = [c for c in detected if not c.needs_creation]

    if config_vault is None:
        if real:
            top = real[0]
            return DiagnosticResult(
                check_id="vault_config_consistency",
                status=DiagnosticStatus.WARN,
                message=(
                    f"config.yaml vault 미설정. 감지된 vault: {top.path} "
                    f"(source={top.source.value}, confidence={top.confidence}). "
                    f"적용하려면 `synapse-memory doctor --fix-config`."
                ),
                fixable=True,
                fix_action_id="set_config_vault",
                target=top.path,
            )
        return DiagnosticResult(
            check_id="vault_config_consistency",
            status=DiagnosticStatus.WARN,
            message=(
                "config.yaml vault 미설정 + 자동 감지 실패. "
                "installer 또는 수동 설정 필요."
            ),
            fixable=False,
        )

    config_path = Path(config_vault).expanduser().resolve()
    if config_path.is_dir():
        return DiagnosticResult(
            check_id="vault_config_consistency",
            status=DiagnosticStatus.OK,
            message=f"config vault: {config_path}",
            target=config_path,
        )

    if real:
        top = real[0]
        return DiagnosticResult(
            check_id="vault_config_consistency",
            status=DiagnosticStatus.WARN,
            message=(
                f"config vault ({config_path}) 가 존재하지 않음. "
                f"감지된 vault: {top.path}. "
                f"적용하려면 `synapse-memory doctor --fix-config`."
            ),
            fixable=True,
            fix_action_id="set_config_vault",
            target=top.path,
        )

    return DiagnosticResult(
        check_id="vault_config_consistency",
        status=DiagnosticStatus.FAIL,
        message=(
            f"config vault ({config_path}) 존재하지 않음 + 자동 감지 실패. "
            "올바른 경로로 `synapse-memory config set vault <path>` 실행."
        ),
        fixable=False,
    )


def apply_set_config_vault(target: Path) -> FixResult:
    """detection 결과를 config.yaml vault 키에 적용.

    명시적 호출 전용 — `apply_fix_actions` 자동 dispatch에 포함되지 않는다.
    silent overwrite 차단을 위해 CLI 의 `doctor --fix-config` 경로 또는
    테스트에서 직접 호출.
    """
    from synapse_memory.config import load_config, save_config

    cfg = load_config()
    old = cfg.vault
    cfg.vault = str(target)
    save_config(cfg)
    return FixResult(
        action_id="set_config_vault",
        status="success",
        summary=f"config.vault: {old!r} → {target}",
    )
