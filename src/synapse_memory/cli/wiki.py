"""wiki and lint commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from synapse_memory.cli.common import OK, api


def cmd_wiki_ask(args: argparse.Namespace) -> int:
    result = api().ask_wiki(args.query, save=getattr(args, "save", False))
    print(result.answer)
    if result.sources:
        print("\n출처: " + ", ".join(f"[[{source}]]" for source in result.sources))
    if result.saved_slug:
        print(f"{OK} insight 저장: {result.saved_slug}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    vault = getattr(args, "vault", None)
    kwargs = {"vault_path": Path(vault)} if vault else {}
    result = api().run_lint(**kwargs)
    print(result.render_plain())
    return 1 if result.has_violations else 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    wiki = subparsers.add_parser("wiki", help="wiki-first 검색 + 답변 환원")
    wiki_sub = wiki.add_subparsers(dest="action", required=True, metavar="ACTION")

    ask = wiki_sub.add_parser("ask", help="wiki 근거 질의 (인용 포함)")
    ask.add_argument("query", help="자연어 질의")
    ask.add_argument("--save", action="store_true", help="답변을 insight 페이지로 환원")
    ask.set_defaults(func=cmd_wiki_ask)

    lint = subparsers.add_parser("lint", help="schema.yaml 검증 + 죽은 링크 자동수정")
    lint.add_argument("--now", action="store_true", help="즉시 1회 실행")
    lint.add_argument("--vault", help="검증할 vault 경로")
    lint.set_defaults(func=cmd_lint)
