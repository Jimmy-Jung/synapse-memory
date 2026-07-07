"""doctor command."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from synapse_memory.cli.common import FAIL, OK, api


def run_doctor_fix(*, assume_yes: bool = False) -> int:
    shim_path = Path.home() / ".synapse" / "bin" / "synapse-memory"
    diagnostics = [api().diagnose_runtime_shim(shim_path)]
    actions = api().planned_fix_actions(diagnostics)

    if not actions:
        ok = all(result.status == "ok" for result in diagnostics)
        print("자동 복구할 항목 없음")
        return 0 if ok else 1

    print("Planned fixes:")
    for index, action in enumerate(actions, start=1):
        print(f"{index}. {action.id} - {action.description} (risk={action.risk})")

    if not assume_yes:
        print("Applying in 0.5s. Press Ctrl+C to cancel.")
        api().time.sleep(0.5)

    applied = api().apply_fix_actions(actions)
    failed = 0
    for result in applied:
        print(f"{result.action_id}: {result.status} - {result.summary}")
        if result.status != "success":
            failed += 1
    return 1 if failed else 0


def run_doctor_fix_config(*, assume_yes: bool = False) -> int:
    from synapse_memory.config import load_config

    cfg = load_config()
    result = api().diagnose_vault_config_consistency(cfg.vault)

    if result.status == api().DiagnosticStatus.OK:
        print(f"{OK} {result.message}")
        return 0

    if not result.fixable or result.target is None:
        print(f"{FAIL} {result.message}")
        return 1

    print("config.yaml vault 갱신 후보:")
    print(f"  현재 config: {cfg.vault!r}")
    print(f"  감지된 vault: {result.target}")
    print(f"  사유: {result.message}")

    if not assume_yes:
        try:
            answer = input("이 경로로 갱신할까요? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("취소됨. config 변경 없음.")
            return 0

    fix_result = api().apply_set_config_vault(result.target)
    print(f"{OK} {fix_result.summary}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    if getattr(args, "fix_config", False):
        return cast(int, api().run_doctor_fix_config(
            assume_yes=bool(getattr(args, "yes", False))
        ))
    if getattr(args, "fix", False):
        return cast(int, api().run_doctor_fix(assume_yes=bool(getattr(args, "yes", False))))

    print("Synapse Memory 환경 진단")
    print("=" * 44)

    try:
        from synapse_memory.config import load_config

        vc_cfg = load_config()
        vc_result = api().diagnose_vault_config_consistency(vc_cfg.vault)
        if vc_result.status == api().DiagnosticStatus.OK:
            print(f"{OK} {vc_result.message}")
        elif vc_result.status == api().DiagnosticStatus.WARN:
            print(f"⚠ {vc_result.message}")
        else:
            print(f"{FAIL} {vc_result.message}")
    except Exception as exc:
        print(f"⚠ vault config 진단 실패: {exc}")

    try:
        from synapse_memory.config import load_config

        wp_cfg = load_config()
        if wp_cfg.vault is None:
            raise ValueError("config.yaml vault 미설정")
        wp_result = api().diagnose_wiki_pages(wp_cfg.vault)
        if wp_result.status == api().DiagnosticStatus.OK:
            print(f"{OK} {wp_result.message}")
        elif wp_result.status == api().DiagnosticStatus.WARN:
            print(f"⚠ {wp_result.message}")
        else:
            print(f"{FAIL} {wp_result.message}")
        for line in api().relation_metrics_lines(wp_cfg.vault):
            print(f"{OK} {line}")
    except Exception as exc:
        print(f"⚠ Entity 진단 실패: {exc}")

    try:
        from synapse_memory.config import describe_privacy_mode, load_config

        wm_result = api().diagnose_wiki_maintenance()
        if wm_result.status == api().DiagnosticStatus.OK:
            print(f"{OK} {wm_result.message}")
        else:
            print(f"⚠ {wm_result.message}")
        cfg = load_config()
        print(f"{OK} Entity maintenance engine: {cfg.maintenance.engine}")
        privacy_mode = describe_privacy_mode(cfg)
        print(f"{OK} privacy mode ingest: {privacy_mode.ingest}")
        print(f"{OK} privacy mode query: {privacy_mode.query}")
    except Exception as exc:
        print(f"⚠ Entity 유지 데몬 진단 실패: {exc}")

    try:
        from synapse_memory.hooks.install import diagnose_session_hook

        hook_result = diagnose_session_hook()
        hook_ready = getattr(hook_result, "ready", hook_result.installed)
        if hook_ready:
            print(f"{OK} {hook_result.message}")
        else:
            print(f"⚠ {hook_result.message}")
            if not hook_result.installed:
                print("  설치: synapse-memory hook install")
            else:
                print("  정비: synapse-memory hook install")
                print("  현재 프로젝트 등록: synapse-memory setup")
                print("  캐시 갱신: synapse-memory context render")
    except Exception as exc:
        print(f"⚠ SessionStart hook 진단 실패: {exc}")

    ai_env = api().detect_ai_environment()
    if ai_env.ready:
        ver = ai_env.version or "(version unknown)"
        print(
            f"{OK} AI provider ({ai_env.provider}): {ai_env.path} [{ver}] "
            f"(model={ai_env.model})"
        )
    else:
        print(f"{FAIL} AI provider ({ai_env.provider}) 사용 불가")
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}")

    print("=" * 44)
    if ai_env.ready:
        print("✓ 준비 완료")
        return 0

    print("환경 미충족:")
    for reason in ai_env.reasons_unavailable():
        print(f"  - {reason}")
    return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("doctor", help="환경 진단 (vault/config/AI provider)")
    parser.add_argument("--fix", action="store_true", help="whitelist 기반 자동 복구")
    parser.add_argument(
        "--fix-config",
        action="store_true",
        help="config.yaml vault 경로를 detection 결과로 갱신 (별도 명시 필요, --fix와 분리)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="doctor --fix preview 후 짧은 대기 생략",
    )
    parser.set_defaults(func=cmd_doctor)
