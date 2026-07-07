"""config and assistant-status commands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict

from synapse_memory.cli.common import FAIL, OK


def cmd_config_show(args: argparse.Namespace) -> int:
    from synapse_memory.config import DEFAULT_CONFIG_PATH, load_config, render_config

    cfg = load_config()
    if args.json:
        print(json.dumps(asdict(cfg), ensure_ascii=False, indent=2))
        return 0
    print(render_config(cfg, show_advanced=args.advanced))
    if not DEFAULT_CONFIG_PATH.exists():
        print()
        print(f"(파일 없음 — default 값. 변경 시 자동 생성: {DEFAULT_CONFIG_PATH})")
    return 0


def cmd_config_get(args: argparse.Namespace) -> int:
    from synapse_memory.config import get_value, load_config

    cfg = load_config()
    try:
        value = get_value(cfg, args.path)
    except KeyError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    print(value if value is not None else "(미설정)")
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    from synapse_memory.config import (
        is_advanced_path,
        is_protected_path,
        load_config,
        save_config,
        set_value,
        validate_config,
    )

    if is_protected_path(args.path):
        print(
            f"{FAIL} 보호된 키 — config로 변경 불가: {args.path}\n"
            "    (보안 핵심 — 코드 PR로만 변경)",
            file=sys.stderr,
        )
        return 3

    cfg = load_config()
    if is_advanced_path(args.path) and not args.force:
        print(
            f"⚠ advanced 키: {args.path}\n"
            "  잘못 변경 시 검색 품질 저하 또는 색인 재생성 필요.\n"
            "  계속하려면 `--force`를 붙이세요.",
            file=sys.stderr,
        )
        return 4

    try:
        set_value(cfg, args.path, args.value)
    except (KeyError, ValueError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2

    errors = validate_config(cfg)
    if errors:
        print(f"{FAIL} 검증 실패:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 5

    save_config(cfg)
    print(f"{OK} {args.path} = {args.value}")
    return 0


def cmd_config_edit(_args: argparse.Namespace) -> int:
    from synapse_memory.config import DEFAULT_CONFIG_PATH, load_config, save_config

    if not DEFAULT_CONFIG_PATH.exists():
        save_config(load_config(), make_backup=False)
        print(f"{OK} default config 작성: {DEFAULT_CONFIG_PATH}")

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        print(
            "EDITOR 환경변수가 없습니다. 직접 열어 편집하세요:\n"
            f"  {DEFAULT_CONFIG_PATH}",
            file=sys.stderr,
        )
        return 0
    return subprocess.run([editor, str(DEFAULT_CONFIG_PATH)], check=False).returncode


def cmd_config_reset(args: argparse.Namespace) -> int:
    from synapse_memory.config import SynapseConfig, get_value, load_config, save_config, set_value

    if args.path is None:
        save_config(SynapseConfig())
        print(f"{OK} 전체 config를 default로 복원")
        return 0

    default_cfg = SynapseConfig()
    try:
        default_val = get_value(default_cfg, args.path)
    except KeyError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2

    cfg = load_config()
    try:
        set_value(cfg, args.path, default_val)
    except (KeyError, ValueError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2

    save_config(cfg)
    print(f"{OK} {args.path}를 default({default_val})로 복원")
    return 0


def cmd_config_validate(_args: argparse.Namespace) -> int:
    from synapse_memory.config import load_config, validate_config

    cfg = load_config()
    errors = validate_config(cfg)
    if not errors:
        print(f"{OK} config 검증 통과")
        return 0
    print(f"{FAIL} 검증 실패 ({len(errors)}건):", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def cmd_assistant_status(args: argparse.Namespace) -> int:
    from synapse_memory.assistant_status import gather_status, render_status

    status = gather_status()
    if args.json:
        print(status.to_json())
    else:
        print(render_status(status))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("config", help="사용자 설정 관리 (~/.synapse/config.yaml)")
    config_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    show = config_sub.add_parser("show", help="현재 효력 있는 config 출력")
    show.add_argument("--json", action="store_true")
    show.add_argument("--advanced", action="store_true", help="advanced 섹션도 포함")
    show.set_defaults(func=cmd_config_show)

    get = config_sub.add_parser("get", help="단일 키 조회")
    get.add_argument("path", help="점 표기 키 경로")
    get.set_defaults(func=cmd_config_get)

    set_cmd = config_sub.add_parser("set", help="단일 키 설정 + 자동 백업")
    set_cmd.add_argument("path", help="점 표기 키 경로")
    set_cmd.add_argument("value", help="설정할 값")
    set_cmd.add_argument("--force", action="store_true")
    set_cmd.set_defaults(func=cmd_config_set)

    edit = config_sub.add_parser("edit", help="$EDITOR로 config.yaml 직접 편집")
    edit.set_defaults(func=cmd_config_edit)

    reset = config_sub.add_parser("reset", help="전체 또는 단일 키를 default로 복원")
    reset.add_argument("path", nargs="?", default=None)
    reset.set_defaults(func=cmd_config_reset)

    validate = config_sub.add_parser("validate", help="현재 config 검증")
    validate.set_defaults(func=cmd_config_validate)

    assistant = subparsers.add_parser(
        "assistant-status",
        help="비서 모드용 read-only 진단 묶음 (vault·doctor·inbox·draft·last-daily)",
    )
    assistant.add_argument("--json", action="store_true")
    assistant.set_defaults(func=cmd_assistant_status)
