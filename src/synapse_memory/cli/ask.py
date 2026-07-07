"""ask command."""

from __future__ import annotations

import argparse
import sys

from synapse_memory.cli.common import FAIL, api


def cmd_ask(args: argparse.Namespace) -> int:
    args.top_k = api()._arg_or_config(args.top_k, "top_k.ask", 5)
    args.model = api()._resolve_model(args.model, "ask")
    api()._enforce_cost_cap("ask")
    api()._interactive_guard("ask", "ask")
    ai_env = api().detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}", file=sys.stderr)
        return 2

    where: dict[str, object] | None = None
    if args.kind:
        where = {"source_kind": f"card_{args.kind}"}

    try:
        # api()=synapse_memory.cli 패키지. cli/ask.py 서브모듈이 패키지의 lazy
        # __getattr__를 shadow해 api().ask가 이 모듈 자신(callable 아님)을 가리킨다.
        # endpoints ask 함수를 직접 import해 이름 충돌을 회피한다.
        from synapse_memory.endpoints.ask import ask as ask_endpoint

        result = ask_endpoint(
            args.query,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
            where=where,
            hybrid=args.hybrid,
            save=args.save,
        )
    except api().AIError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    print(f"질문: {result.query}\n")
    print(result.answer)
    print()
    print("=" * 60)
    print(f"출처 ({len(result.sources)}):")
    for source in result.sources:
        print(f"  {source.source_kind:<14} {source.card_id} — {source.display_name}")
    if result.saved_path is not None:
        print()
        print(f"저장: {result.saved_path}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "ask",
        help="자연어 질의 → provider 선별 → AI 답변",
        description="자연어 질의를 CardIndex와 provider 선별 결과로 답변합니다.",
    )
    parser.add_argument("query", help="자연어 질문")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--kind", choices=["project", "company"])
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="호환 플래그: provider-only에서는 ranking 차이 없음",
    )
    parser.add_argument("--save", action="store_true", help="답변을 InsightCard로 저장")
    parser.set_defaults(func=cmd_ask)
