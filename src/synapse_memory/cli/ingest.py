"""ingest, backfill, compact, and raw collect commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from synapse_memory.cli.common import FAIL, api
from synapse_memory.formatting import _format_bytes


def cmd_ingest(args: argparse.Namespace) -> int:
    dry = bool(getattr(args, "dry_run", False))
    try:
        locked_result = api().run_with_ingest_lock(
            source=args.source,
            mode="manual",
            on_locked="fail",
            operation=lambda: api().ingest_source(
                args.source,
                dry_run=dry,
                limit=args.limit,
                semantic_retrieval=not args.no_semantic_retrieval,
            ),
        )
    except Exception as exc:
        if exc.__class__.__name__ == "IngestAlreadyRunningError":
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        raise
    if not isinstance(locked_result, api().IngestResult):
        print(f"{FAIL} ingest already running: {locked_result.reason}", file=sys.stderr)
        return 1
    result = locked_result
    label = "(dry-run) " if dry else ""
    print(
        f"{label}ingest {result.source}: docs={result.docs_processed}, "
        f"pages={len(result.pages_written)}, skipped={result.docs_skipped}"
    )
    if result.pages_written:
        print("  written: " + ", ".join(result.pages_written))
    if result.errors:
        print(f"  errors: {len(result.errors)}")
        for error in result.errors:
            print(f"    - {error}")
    return 1 if result.errors else 0


def cmd_ingest_audit(args: argparse.Namespace) -> int:
    result = api().audit_ingest_queue(
        args.source,
        limit=args.limit,
        min_age_seconds=args.min_age_seconds,
        semantic_retrieval=not args.no_semantic_retrieval,
    )
    if args.json:
        from dataclasses import asdict

        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0

    print(
        f"ingest-audit {result.source}: pending={result.docs_pending}, "
        f"small={result.docs_small}, sampled={result.docs_sampled}, "
        f"oversize={result.docs_oversize}, "
        f"estimated_llm_calls={result.estimated_llm_calls}, "
        f"max_chars={result.max_chars}"
    )
    print(
        f"privacy_mode={result.privacy_mode}, "
        f"provider_payload={result.provider_payload}"
    )
    print(f"privacy_note: {result.privacy_note}")
    return 0


def _confirm_apply_compact(args: argparse.Namespace) -> bool:
    if not args.apply or args.yes:
        return True
    action = "rehydrate" if args.rehydrate else "compact"
    if not sys.stdin.isatty():
        print(f"{FAIL} --apply requires --yes in non-interactive mode", file=sys.stderr)
        return False
    answer = input(f"raw mirror {action}를 적용할까요? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def cmd_compact_raw(args: argparse.Namespace) -> int:
    if not _confirm_apply_compact(args):
        return 2
    sources = ("claude-code", "codex") if args.source == "all" else (args.source,)
    results = []
    for source in sources:
        def operation(target: str = source) -> object:
            return api().compact_mirror_source(
                target,
                apply=bool(args.apply),
                rehydrate=bool(args.rehydrate),
            )

        outcome = api().run_with_ingest_lock(
            source=source,
            mode="compact",
            on_locked="wait",
            operation=operation,
        )
        if isinstance(outcome, api().CompactSourceResult):
            results.append(outcome)

    verb = "rehydrate" if args.rehydrate else "compact-raw"
    mode = "apply" if args.apply else "dry-run"
    for result in results:
        print(
            f"{verb} {result.source} ({mode}): "
            f"seen={result.files_seen} eligible={result.files_eligible} "
            f"changed={result.files_changed} skipped={result.files_skipped} "
            f"aborted={result.files_aborted} "
            f"reclaimable={_format_bytes(result.bytes_reclaimable)}"
        )
        for error in result.errors:
            print(f"  error: {error}", file=sys.stderr)
    if not args.apply:
        print(
            "dry-run: 파일 변경 없음. --apply --yes 적용 시 drop 라인은 "
            ".toolio.jsonl.gz sidecar에 저장되며, 원복은 --rehydrate --apply --yes."
        )
    return 1 if any(result.errors for result in results) else 0


def cmd_backfill(args: argparse.Namespace) -> int:
    try:
        result = api().run_backfill(
            source=args.source,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            semantic_retrieval=not args.no_semantic_retrieval,
            wait_lock=args.wait_lock,
        )
    except Exception as exc:
        if exc.__class__.__name__ == "IngestAlreadyRunningError":
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        raise
    print(
        f"backfill {result.source}: {result.batches} batches, "
        f"{result.docs_processed} docs, {len(result.pages_written)} pages, "
        f"skipped={result.docs_skipped}"
    )
    if result.errors:
        print(f"  errors: {len(result.errors)}")
    return 1 if result.errors else 0


def cmd_collect_obsidian(args: argparse.Namespace) -> int:
    vault: Path = args.vault.expanduser().resolve()
    dst_root: Path = args.dst.expanduser().resolve()

    if not vault.is_dir():
        print(f"{FAIL} vault 없음: {vault}", file=sys.stderr)
        print(
            "  --vault PATH로 지정하거나 SYNAPSE_OBSIDIAN_VAULT 환경변수 설정",
            file=sys.stderr,
        )
        return 2

    print(f"수집 시작: {vault} → {dst_root}")
    stats = api().collect_obsidian(vault_path=vault, dst_root=dst_root)
    print(stats.summary())

    if stats.errors:
        print("에러:", file=sys.stderr)
        for path, msg in stats.errors:
            print(f"  {path}: {msg}", file=sys.stderr)
        return 1
    return 0


def cmd_collect_claude_code(args: argparse.Namespace) -> int:
    claude_home: Path = args.src.expanduser().resolve()
    dst_root: Path = args.dst.expanduser().resolve()

    if not claude_home.is_dir():
        print(f"{FAIL} Claude home 없음: {claude_home}", file=sys.stderr)
        return 2

    print(f"수집 시작: {claude_home} → {dst_root}")
    stats = api().collect_claude_code(claude_home=claude_home, dst_root=dst_root)
    print(stats.summary())

    if stats.errors:
        print("에러:", file=sys.stderr)
        for path, msg in stats.errors:
            print(f"  {path}: {msg}", file=sys.stderr)
        return 1
    return 0


def cmd_collect_codex(args: argparse.Namespace) -> int:
    codex_home: Path = args.src.expanduser().resolve()
    dst_root: Path = args.dst.expanduser().resolve()

    if not codex_home.is_dir():
        print(f"{FAIL} Codex home 없음: {codex_home}", file=sys.stderr)
        return 2

    print(f"수집 시작: {codex_home} → {dst_root}")
    stats = api().collect_codex(codex_home=codex_home, dst_root=dst_root)
    print(stats.summary())

    if stats.errors:
        print("에러:", file=sys.stderr)
        for path, msg in stats.errors:
            print(f"  {path}: {msg}", file=sys.stderr)
        return 1
    return 0


def _add_ingest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default="claude-code", choices=["claude-code", "codex"])
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 doc 수")
    parser.add_argument(
        "--no-semantic-retrieval",
        action="store_true",
        help="provider 기반 관련 페이지 선별을 끄고 통합 호출만 수행",
    )


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    collect = subparsers.add_parser("collect", help="외부 데이터 수집")
    collect_sub = collect.add_subparsers(dest="source", required=True, metavar="SOURCE")

    p_cc = collect_sub.add_parser("claude-code", help="Claude Code 로그를 L0로 mirror")
    p_cc.add_argument("--src", type=Path, default=Path.home() / ".claude")
    p_cc.add_argument(
        "--dst",
        type=Path,
        default=api().l0_root() / "raw" / "claude-code",
        help="L0 mirror 루트 (기본: ~/.synapse/private/raw/claude-code)",
    )
    p_cc.set_defaults(func=cmd_collect_claude_code)

    p_codex = collect_sub.add_parser("codex", help="Codex 세션 로그를 L0로 mirror")
    p_codex.add_argument("--src", type=Path, default=Path.home() / ".codex")
    p_codex.add_argument(
        "--dst",
        type=Path,
        default=api().l0_root() / "raw" / "codex",
        help="L0 mirror 루트 (기본: ~/.synapse/private/raw/codex)",
    )
    p_codex.set_defaults(func=cmd_collect_codex)

    p_obs = collect_sub.add_parser("obsidian", help="Obsidian vault를 L0로 mirror")
    p_obs.add_argument(
        "--vault",
        type=Path,
        default=api().get_vault_path(),
        help=f"Vault 경로 (기본: {api().get_vault_path()})",
    )
    p_obs.add_argument(
        "--dst",
        type=Path,
        default=api().l0_root() / "raw" / "obsidian",
        help="L0 mirror 루트 (기본: ~/.synapse/private/raw/obsidian)",
    )
    p_obs.set_defaults(func=cmd_collect_obsidian)

    ingest = subparsers.add_parser("ingest", help="wiki ingest 엔진 (raw 대화 → wiki 통합)")
    ingest.add_argument("--now", action="store_true", help="즉시 1회 ingest")
    ingest.add_argument("--dry-run", action="store_true", help="적용 없이 결과만 표시")
    _add_ingest_args(ingest)
    ingest.set_defaults(func=cmd_ingest)

    audit = subparsers.add_parser(
        "ingest-audit",
        help="watermark 이후 raw queue 비용과 raw/sample provider 전송 정책을 LLM 호출 없이 점검",
    )
    _add_ingest_args(audit)
    audit.add_argument("--min-age-seconds", type=float, default=None)
    audit.add_argument("--json", action="store_true", help="JSON 출력")
    audit.set_defaults(func=cmd_ingest_audit)

    compact = subparsers.add_parser(
        "compact-raw",
        help="이미 ingest된 raw mirror를 gzip sidecar로 수동 축소",
    )
    compact.add_argument(
        "--source",
        default="all",
        choices=["all", "claude-code", "codex"],
        help="대상 raw source (기본: all)",
    )
    compact.add_argument("--apply", action="store_true", help="실제 파일 변경 적용")
    compact.add_argument("--yes", action="store_true", help="--apply 확인 생략")
    compact.add_argument("--rehydrate", action="store_true", help="sidecar에서 복원")
    compact.set_defaults(func=cmd_compact_raw)

    backfill = subparsers.add_parser(
        "backfill",
        help="빈 vault 재구축 — 전체 raw 이력을 배치로 ingest (재개 가능)",
    )
    backfill.add_argument("--source", default="claude-code", choices=["claude-code", "codex"])
    backfill.add_argument("--batch-size", type=int, default=20)
    backfill.add_argument("--max-batches", type=int, default=None)
    backfill.add_argument("--wait-lock", action="store_true")
    backfill.add_argument("--no-semantic-retrieval", action="store_true")
    backfill.set_defaults(func=cmd_backfill)
