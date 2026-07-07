"""hook command."""

from __future__ import annotations

import argparse
import sys

from synapse_memory.cli.common import FAIL, OK, api


def cmd_hook(args: argparse.Namespace) -> int:
    if args.action == "run":
        from synapse_memory.hooks.session_start import main as hook_main

        return hook_main()

    if args.action == "install":
        from synapse_memory.hooks.install import install_session_hook

        try:
            changed = install_session_hook()
        except ValueError as exc:
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        api()._refresh_hook_sidecars()
        action = "설치됨" if changed else "이미 설치됨"
        print(f"{OK} Claude Code/Codex SessionStart hook {action}")
        print("  Codex는 첫 실행 전 `/hooks`에서 hook 신뢰 승인이 필요할 수 있습니다.")
        return 0

    if args.action == "uninstall":
        from synapse_memory.hooks.install import uninstall_session_hook

        try:
            changed = uninstall_session_hook()
        except ValueError as exc:
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        action = "제거됨" if changed else "설치 항목 없음"
        print(f"{OK} Claude Code/Codex SessionStart hook {action}")
        return 0

    print(f"{FAIL} unknown hook action: {args.action}", file=sys.stderr)
    return 2


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("hook", help="Claude Code/Codex SessionStart hook 관리")
    hook_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    install = hook_sub.add_parser("install", help="SessionStart hook 설치")
    install.set_defaults(func=cmd_hook)

    uninstall = hook_sub.add_parser("uninstall", help="SessionStart hook 제거")
    uninstall.set_defaults(func=cmd_hook)

    run = hook_sub.add_parser("run", help="SessionStart hook 실행")
    run.add_argument(
        "--event",
        choices=("session-start",),
        required=True,
        help="hook event 이름",
    )
    run.set_defaults(func=cmd_hook)
