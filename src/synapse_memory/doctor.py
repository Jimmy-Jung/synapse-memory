"""구조화된 doctor 진단 및 whitelist repair.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
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


def diagnose_wiki_pages(vault: Path | str) -> DiagnosticResult:
    """v2 Entity 존재 점검 — entity/concept/profile/insight 합산 카운트."""
    from synapse_memory.model import ENTITY_TYPES
    from synapse_memory.store import list_pages

    vault_root = Path(vault).expanduser()
    total = 0
    for page_type in ENTITY_TYPES:
        total += len(list_pages(page_type, vault_path=vault_root))

    if total == 0:
        return DiagnosticResult(
            check_id="wiki_pages",
            status=DiagnosticStatus.WARN,
            message=(
                "v2 Entity 0개 — 아직 생성되지 않음. "
                "`synapse-memory daily` 또는 `/sm:daily`로 온톨로지를 구축하세요."
            ),
            target=vault_root,
        )
    return DiagnosticResult(
        check_id="wiki_pages",
        status=DiagnosticStatus.OK,
        message=f"v2 Entity {total}개",
        target=vault_root,
    )


def _parse_watermark(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _recent_watch_errors(
    path: Path,
    *,
    limit: int = 3,
    fresh_after: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> list[str]:
    if not path.is_file():
        return []
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except OSError:
        return []
    reference_now = now or datetime.now().astimezone()
    if reference_now - modified_at > fresh_after:
        return []
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return []
    return [line for line in lines if line][-limit:]


def diagnose_wiki_maintenance(
    *,
    home: Path | None = None,
    state_path: Path | None = None,
    err_log_path: Path | None = None,
    sources: tuple[str, ...] = ("claude-code", "codex"),
    stale_after: timedelta = timedelta(days=7),
    error_fresh_after: timedelta = timedelta(hours=24),
) -> DiagnosticResult:
    """v2 wiki 자동 유지 watch 데몬(launchd LaunchAgent) 설치 점검."""
    from synapse_memory.storage.l0 import l0_root
    from synapse_memory.wiki.launchd import plist_path
    from synapse_memory.wiki.watermark import load_watermark

    path = plist_path(home=home)
    if path.is_file():
        issues: list[str] = []
        now = datetime.now().astimezone()
        for source in sources:
            watermark = load_watermark(source, path=state_path)
            if watermark is None:
                issues.append(f"{source} watermark 없음")
                continue
            parsed = _parse_watermark(watermark)
            if parsed is None:
                issues.append(f"{source} watermark 파싱 실패")
                continue
            if now - parsed.astimezone() > stale_after:
                issues.append(f"{source} watermark stale: {watermark}")
        errors = _recent_watch_errors(
            err_log_path or (l0_root() / "watch.err.log"),
            fresh_after=error_fresh_after,
            now=now,
        )
        if errors:
            issues.append(f"watch.err.log 최근 오류 {len(errors)}건")
        if issues:
            return DiagnosticResult(
                check_id="wiki_maintenance",
                status=DiagnosticStatus.WARN,
                message=f"wiki watch 데몬 설치됨: {path}; " + "; ".join(issues),
                target=path,
            )
        return DiagnosticResult(
            check_id="wiki_maintenance",
            status=DiagnosticStatus.OK,
            message=f"wiki watch 데몬 설치됨: {path}; sources fresh: {', '.join(sources)}",
            target=path,
        )
    return DiagnosticResult(
        check_id="wiki_maintenance",
        status=DiagnosticStatus.WARN,
        message=(
            f"wiki watch 데몬 미설치 ({path} 없음) — 자동 유지 비활성. "
            "설치: `synapse-memory watch install`."
        ),
        target=path,
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
        if result.fix_action_id == "recreate_runtime_shim" and result.target is not None:
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


def _runtime_rerun_guidance(target: Path) -> FixResult:
    return FixResult(
        action_id="recreate_runtime_shim",
        status="manual_required",
        summary=f"{target} 재생성은 scripts/bootstrap_runtime.sh 재실행 필요",
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
                "수동 설정 필요."
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
