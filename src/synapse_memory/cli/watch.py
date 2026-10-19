"""watch command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from synapse_memory.cli.common import FAIL, api

_WATCH_SOURCES = ("claude-code", "codex")


def cmd_watch_run(args: argparse.Namespace) -> int:
    total_docs = 0
    total_docs_skipped = 0
    total_pages: list[str] = []
    total_errors: list[object] = []
    skipped: list[str] = []

    for source in _WATCH_SOURCES:
        outcome = api().run_watch_cycle(source=source)
        if not outcome.ran:
            skipped.append(f"{source}:{outcome.skipped_reason}")
            continue
        result = outcome.result
        total_pages.extend(getattr(result, "pages_written", []) or [])
        total_docs += getattr(result, "docs_processed", 0)
        total_docs_skipped += getattr(result, "docs_skipped", 0)
        total_errors.extend(getattr(result, "errors", []) or [])

    print(
        f"watch run: docs={total_docs}, pages={len(total_pages)}, "
        f"errors={len(total_errors)}, skipped={total_docs_skipped}"
    )
    if total_pages:
        print("  written: " + ", ".join(total_pages))
    if skipped:
        print("  skipped: " + ", ".join(skipped))
    for error in total_errors:
        print(f"  error: {error}", file=sys.stderr)
    return 1 if total_errors else 0


def _choose_log_dir(flag: str | None) -> Path:
    """우선순위: --log-dir > config 저장값 > (터미널이면) 최초 설치 프롬프트 > 기본값."""
    from synapse_memory.config import load_config
    from synapse_memory.wiki.launchd import default_log_dir

    if flag:
        return Path(flag)
    configured = load_config().maintenance.log_dir
    if configured:
        return Path(configured)
    default = default_log_dir()
    if not sys.stdin.isatty():
        return default
    answer = input(f"watch 로그 저장 경로 (내장 디스크) [{default}]: ").strip()
    return Path(answer) if answer else default


def _remember_log_dir(log_dir: Path) -> None:
    """선택한 경로를 config에 저장 — 재설치 때 다시 묻지 않는다."""
    from synapse_memory.config import load_config, save_config

    cfg = load_config()
    if cfg.maintenance.log_dir == str(log_dir):
        return
    cfg.maintenance.log_dir = str(log_dir)
    save_config(cfg)


def cmd_watch_install(args: argparse.Namespace) -> int:
    from synapse_memory.wiki.launchd import check_log_dir

    try:
        log_dir = check_log_dir(_choose_log_dir(args.log_dir))
        path = api().install_watch(log_dir=log_dir)
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except api().LaunchctlError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    _remember_log_dir(log_dir)
    print(f"installed: {path}")
    print(f"logs: {log_dir}")
    return 0


def cmd_watch_uninstall(args: argparse.Namespace) -> int:
    try:
        api().uninstall_watch()
    except api().LaunchctlError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    print("uninstalled")
    return 0


def cmd_watch_status(args: argparse.Namespace) -> int:
    from synapse_memory.wiki.launchd import plist_path

    path = plist_path()
    installed = path.exists()
    sources = [
        {"source": source, "watermark": api().load_watermark(source)}
        for source in _WATCH_SOURCES
    ]
    if args.json:
        print(
            json.dumps(
                {"installed": installed, "plist": str(path), "sources": sources},
                ensure_ascii=False,
            )
        )
        return 0
    print(f"installed: {installed} ({path})")
    for entry in sources:
        print(f"{entry['source']} watermark: {entry['watermark'] or '(none)'}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "watch", help="자동 통합 데몬 (launchd StartInterval + 유휴 + 락)"
    )
    watch_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    run = watch_sub.add_parser("run", help="watch 사이클 1회 실행")
    run.set_defaults(func=cmd_watch_run)

    install = watch_sub.add_parser("install", help="launchd LaunchAgent 설치")
    install.add_argument(
        "--log-dir",
        default=None,
        help="watch 로그 디렉터리 (내장 디스크, 기본 ~/.synapse/logs). config에 저장된다.",
    )
    install.set_defaults(func=cmd_watch_install)

    uninstall = watch_sub.add_parser("uninstall", help="launchd LaunchAgent 제거")
    uninstall.set_defaults(func=cmd_watch_uninstall)

    status = watch_sub.add_parser("status", help="설치 여부 + watermark")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_watch_status)
