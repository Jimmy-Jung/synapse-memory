"""models command — codex 모델을 카탈로그 기준 최신으로 갱신.

저자: JunyoungJung
작성일: 2026-10-19
"""

from __future__ import annotations

import argparse
import sys

from synapse_memory.cli.common import FAIL, OK


def cmd_models_refresh(args: argparse.Namespace) -> int:
    from synapse_memory.config import load_config, save_config
    from synapse_memory.llm.codex_catalog import apply_changes, load_catalog, pending_changes

    catalog = load_catalog()
    if catalog is None:
        print(
            f"{FAIL} codex 모델 카탈로그 조회 실패(`codex debug models`) — 기존 설정 유지",
            file=sys.stderr,
        )
        return 1
    cfg = load_config()
    changes = pending_changes(cfg.models, catalog)
    if not changes:
        print(f"{OK} codex 모델 최신 (기본 {catalog[0]})")
        return 0

    print("codex 모델 변경 제안 (기본·고급 = 카탈로그 1순위, 저가 = 최신 luna):")
    for task, current, proposed in changes:
        print(f"  {task:<15} {current or '(미설정)'} → {proposed}")
    if args.dry_run:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("적용하려면 --yes를 붙이세요.")
            return 0
        if input("적용할까요? [y/N]: ").strip().lower() not in ("y", "yes"):
            print("취소했습니다.")
            return 0
    apply_changes(cfg.models, changes)
    save_config(cfg)
    print(f"{OK} config에 저장했습니다 (models.overrides.codex).")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("models", help="AI 모델 관리 (codex 카탈로그 기준 최신화)")
    models_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    refresh = models_sub.add_parser("refresh", help="codex 모델을 카탈로그 기준 최신으로 갱신")
    mode = refresh.add_mutually_exclusive_group()
    mode.add_argument("--yes", action="store_true", help="확인 없이 적용 (설치 스크립트용)")
    mode.add_argument("--dry-run", action="store_true", help="제안만 출력")
    refresh.set_defaults(func=cmd_models_refresh)
