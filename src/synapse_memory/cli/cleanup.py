"""cleanup and migrate-folders commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from synapse_memory.cli.common import api


def cmd_cleanup_scan(args: argparse.Namespace) -> int:
    from synapse_memory.cleanup import scan_cleanup_candidates

    vault = api()._resolve_vault(require_exists=True)
    plan = scan_cleanup_candidates(
        vault,
        inbox_stale_days=args.inbox_days,
        dormant_project_days=args.dormant_days,
        old_resume_days=args.resume_days,
        stale_memory_inbox_days=args.memory_inbox_days,
        old_daily_reports_days=args.report_days,
    )
    if args.json:
        print(plan.to_json())
        return 0

    by_kind = plan.by_kind()
    if not plan.candidates:
        print("정리 후보 없음 — vault가 깨끗합니다.")
        return 0
    print(f"vault: {plan.vault_path}")
    print(f"scanned_at: {plan.scanned_at}")
    print(f"총 후보: {len(plan.candidates)}건\n")
    for kind, items in by_kind.items():
        print(f"[{kind}] {len(items)}건")
        for candidate in items[:5]:
            age_part = f" ({candidate.age_days}일)" if candidate.age_days is not None else ""
            print(f"  - {candidate.source_path}{age_part} — {candidate.reason}")
        if len(items) > 5:
            print(f"  ... 외 {len(items) - 5}건")
        print()
    print("실제 이동하려면: `synapse-memory cleanup apply --apply [--category <kind1,kind2>]`")
    return 0


def cmd_cleanup_apply(args: argparse.Namespace) -> int:
    from synapse_memory.cleanup import (
        apply_cleanup,
        scan_cleanup_candidates,
        write_cleanup_manifest,
    )

    vault = api()._resolve_vault(require_exists=True)
    plan = scan_cleanup_candidates(
        vault,
        inbox_stale_days=args.inbox_days,
        dormant_project_days=args.dormant_days,
        old_resume_days=args.resume_days,
        stale_memory_inbox_days=args.memory_inbox_days,
        old_daily_reports_days=args.report_days,
    )

    selected = plan.candidates
    if args.category:
        wanted = {category.strip() for category in args.category.split(",") if category.strip()}
        selected = [candidate for candidate in selected if candidate.kind.value in wanted]
    if not selected:
        print("선택된 후보 없음.")
        return 0

    dry_run = args.dry_run or not args.apply
    results = apply_cleanup(plan, selected=selected, dry_run=dry_run, vault=vault)
    manifest = write_cleanup_manifest(vault, results)

    moved = sum(1 for result in results if result.status == "moved")
    dry = sum(1 for result in results if result.status == "dry_run")
    skipped = sum(1 for result in results if result.status == "skipped")
    failed = sum(1 for result in results if result.status == "failed")

    if dry_run:
        print(f"dry-run: 이동 예정 {dry}건, 건너뜀 {skipped}건. 실제 적용은 `--apply`를 붙이세요.")
    else:
        print(f"이동 {moved}건, 건너뜀 {skipped}건, 실패 {failed}건. 매니페스트: {manifest}")
    return 0 if failed == 0 else 1


def cmd_migrate_folders(args: argparse.Namespace) -> int:
    from synapse_memory.config import get_config
    from synapse_memory.folders.migrate import (
        DAILY_REPORT_PATTERN,
        PROFILE_PATTERN,
        execute_migration,
        scan_flat_files,
    )

    vault = api()._resolve_vault(args, require_exists=True)
    cfg = get_config()
    targets = [
        (vault / cfg.vault_folders.system.ai.memory_inbox, PROFILE_PATTERN, "MemoryInbox"),
        (vault / cfg.vault_folders.system.ai.daily_reports, DAILY_REPORT_PATTERN, "DailyReports"),
    ]

    total_conflicts = 0
    total_skipped: list[Path] = []
    total_errors: list[tuple[Path, str]] = []
    for base, pattern, label in targets:
        plans, skipped = scan_flat_files(base, pattern)
        total_skipped.extend(skipped)
        if not plans and not skipped:
            print(f"  {label:<14} (대상 없음)")
            continue
        result = execute_migration(plans, dry_run=args.dry_run)
        total_conflicts += len(result.conflicts)
        total_errors.extend(result.errors)
        prefix = "  dry-run" if args.dry_run else "  이동"
        print(
            f"{prefix} {label:<14} {len(result.moved)}건, "
            f"충돌 {len(result.conflicts)}건, skipped {len(skipped)}건"
        )
        for plan in result.moved:
            arrow = "→" if not args.dry_run else "·"
            print(f"    {plan.src.name} {arrow} {plan.dst.relative_to(base)}")
        for src, dst in result.conflicts:
            print(f"    ⚠ 충돌: {src.name} (대상 {dst.relative_to(base)} 이미 존재)", file=sys.stderr)
        for src, err in result.errors:
            print(f"    ✖ 실패: {src.name} — {err}", file=sys.stderr)

    if args.report_unknown and total_skipped:
        print("\n[skipped — 패턴 불일치]")
        for path in total_skipped:
            print(f"  {path}")

    if total_errors:
        return 2
    if total_conflicts:
        return 1
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    cleanup = subparsers.add_parser(
        "cleanup",
        help="vault 청소 도우미 (오래된·휴면·빈 자료를 archive로 이동)",
    )
    cleanup_sub = cleanup.add_subparsers(dest="action", required=True, metavar="ACTION")

    scan = cleanup_sub.add_parser("scan", help="청소 후보 read-only 출력")
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--inbox-days", type=int, default=30)
    scan.add_argument("--dormant-days", type=int, default=90)
    scan.add_argument("--resume-days", type=int, default=90)
    scan.add_argument("--memory-inbox-days", type=int, default=60)
    scan.add_argument("--report-days", type=int, default=90)
    scan.add_argument("--dry-run", action="store_true", help="호환용 no-op")
    scan.set_defaults(func=cmd_cleanup_scan)

    apply = cleanup_sub.add_parser("apply", help="선택된 청소 후보를 archive로 이동")
    mode = apply.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    apply.add_argument("--category")
    apply.add_argument("--inbox-days", type=int, default=30)
    apply.add_argument("--dormant-days", type=int, default=90)
    apply.add_argument("--resume-days", type=int, default=90)
    apply.add_argument("--memory-inbox-days", type=int, default=60)
    apply.add_argument("--report-days", type=int, default=90)
    apply.set_defaults(func=cmd_cleanup_apply)

    migrate = subparsers.add_parser(
        "migrate-folders",
        help="기존 flat MemoryInbox/DailyReports 파일을 {YYYY}/{MM}/ 구조로 이동",
    )
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--report-unknown", action="store_true")
    migrate.add_argument("--vault", default=None)
    migrate.set_defaults(func=cmd_migrate_folders)
