"""daily command."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import os
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

from synapse_memory.cli.common import FAIL, OK, api


def cmd_daily(args: argparse.Namespace) -> int:
    try:
        only = api()._parse_stage_csv(args.only) if args.only else None
        skip = api()._parse_stage_csv(args.skip) if args.skip else None
        with api()._daily_status_watcher(
            enabled=bool(args.watch_status and not args.dry_run),
            interval=float(args.status_interval),
        ):
            result = api().run_daily(
                only=only,
                skip=skip,
                resume_from=args.resume_from,
                ingest_model=args.model,
                dry_run=args.dry_run,
            )
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except api().DailyAlreadyRunningError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 3

    if args.dry_run:
        return 0

    print("\n" + "=" * 60)
    print(f"Daily 총 시간: {result.total_elapsed:.1f}s")
    print(
        f"실행 단계: {len(result.steps)}, 실패: {result.errors}, "
        f"경고: {result.warnings}, 건너뜀: {result.skipped}"
    )
    for step in result.steps:
        if step.status == api().StageStatus.SKIPPED:
            status = "-"
            detail = f"skipped: {step.skip_reason}"
        else:
            status = OK if step.ok else FAIL
            detail = step.summary or step.error
        print(f"  {status} {step.name:<22} {step.elapsed:>6.1f}s  {detail}")
    from synapse_memory.status import STATUS_FILE as daily_status_file

    print(f"\n진행률 status: {daily_status_file}  ('synapse-memory daily-status'로 조회)")
    return 1 if result.errors else 0


def _parse_stage_csv(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


@contextlib.contextmanager
def _daily_status_watcher(*, enabled: bool, interval: float) -> Iterator[None]:
    if not enabled:
        yield
        return

    from synapse_memory.status import read_status

    stop = threading.Event()
    pid = os.getpid()
    last_signature: tuple[object, ...] | None = None
    poll_interval = max(0.5, interval)

    def watch() -> None:
        nonlocal last_signature
        while not stop.wait(poll_interval):
            status = read_status()
            if status is None or status.pid != pid:
                continue
            signature = (
                status.state,
                status.current_stage,
                status.current_stage_index,
                status.current_item,
                status.current_item_index,
                status.current_item_total,
                tuple(status.completed_stages),
                tuple(status.failed_stages),
            )
            if signature == last_signature:
                continue
            last_signature = signature
            print(_format_daily_status_line(status), flush=True)

    thread = threading.Thread(target=watch, name="daily-status-watch", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)


def _format_daily_status_line(status: Any) -> str:
    if status.current_stage:
        head = (
            f"[daily-status] {status.current_stage} "
            f"({status.current_stage_index}/{status.total_stages})"
        )
    else:
        head = f"[daily-status] {status.state}"
    if status.current_item_total:
        pct = int(status.current_item_index / status.current_item_total * 100)
        head += (
            f" — {status.current_item} "
            f"[{status.current_item_index}/{status.current_item_total}, {pct}%]"
        )
    if status.failed_stages:
        head += f" — failed: {', '.join(status.failed_stages)}"
    return head


def cmd_daily_status(args: argparse.Namespace) -> int:
    from synapse_memory.status import STATUS_FILE, read_status, render_status

    def print_once() -> int:
        status = read_status()
        if args.json:
            print("{}" if status is None else status.to_json())
        else:
            print(render_status(status))
        return 0 if status is not None else 1

    if not args.watch:
        return print_once()

    interval = max(0.5, float(args.interval))
    last_signature: tuple[str, str, int, str] | None = None
    print(f"watching {STATUS_FILE} (Ctrl-C로 종료, {interval:.1f}s 간격)")
    try:
        while True:
            status = read_status()
            signature: tuple[str, str, int, str] | None = (
                None
                if status is None
                else (
                    status.updated_at,
                    status.current_stage,
                    status.current_item_index,
                    status.state,
                )
            )
            if signature != last_signature:
                print("\n--- " + datetime.datetime.now().isoformat(timespec="seconds"))
                print(render_status(status))
                last_signature = signature
            if status is not None and status.state in {"done", "failed"}:
                return 0 if status.state == "done" else 1
            time.sleep(interval)
    except KeyboardInterrupt:
        return 130


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    daily = subparsers.add_parser("daily", help="일일 통합 파이프라인 (5분 워크플로)")
    daily.add_argument(
        "--only",
        help=f"이 단계들만 (comma-separated). 가능: {','.join(api().STEPS)}",
    )
    daily.add_argument("--skip", help="제외할 단계 (comma-separated)")
    daily.add_argument("--resume-from", choices=api().STEPS, help="지정 stage부터 daily 재개")
    daily.add_argument(
        "--model",
        default=None,
        help="ingest 단계에 사용할 단일 AI 모델 (생략 시 provider default)",
    )
    daily.add_argument(
        "--watch-status",
        action="store_true",
        help="daily 실행 중 status 파일을 폴링해 stage 진행률을 한 줄씩 출력",
    )
    daily.add_argument("--status-interval", type=float, default=2.0)
    daily.add_argument("--dry-run", action="store_true", help="실행 안 하고 단계만")
    daily.set_defaults(func=cmd_daily)

    status = subparsers.add_parser(
        "daily-status",
        help="진행 중인/마지막 daily 진행률 조회 (~/.synapse/run/daily.status.json)",
    )
    status.add_argument("--json", action="store_true", help="JSON 원본 그대로 출력")
    status.add_argument("--watch", action="store_true")
    status.add_argument("--interval", type=float, default=2.0)
    status.set_defaults(func=cmd_daily_status)
