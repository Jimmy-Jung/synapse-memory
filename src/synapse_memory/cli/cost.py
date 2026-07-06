"""cost command."""

from __future__ import annotations

import argparse
import sys

from synapse_memory.cli.common import FAIL, api


def cmd_cost_summary(args: argparse.Namespace) -> int:
    args.days = api()._arg_or_config(args.days, "cost.summary_days", 30)
    if args.days < 1:
        print("--days must be >= 1", file=sys.stderr)
        return 1
    try:
        summary = api().load_summary(days=args.days, by=args.by)
    except (OSError, ValueError) as exc:
        print(f"{FAIL} cost summary 실패: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(api().render_summary_json(summary))
    else:
        print(api().render_summary_table(summary))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("cost", help="비용/토큰 관측")
    cost_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    summary = cost_sub.add_parser("summary", help="최근 비용 요약")
    summary.add_argument("--days", type=int, default=None)
    summary.add_argument("--by", choices=("command", "model"), default="command")
    summary.add_argument("--json", action="store_true", help="JSON 출력")
    summary.set_defaults(func=cmd_cost_summary)
