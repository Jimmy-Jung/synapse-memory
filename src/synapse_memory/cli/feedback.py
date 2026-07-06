"""feedback command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from synapse_memory.cli.common import FAIL, OK, api


def cmd_feedback(args: argparse.Namespace) -> int:
    try:
        action = _feedback_action(args)
        if action == "reject" and not str(args.reject or "").strip():
            raise ValueError("reject feedback reason is required")
        targets = _feedback_targets(args)
        if not targets:
            print("No feedback targets resolved.", file=sys.stderr)
            return 1

        events = []
        last_ref = api().load_last_answer() if args.feedback_target == "last" else None
        for target in targets:
            events.append(
                api().build_feedback_event(
                    target_kind=target.target_kind,
                    target_ref=target.target_ref,
                    action=action,
                    reason=args.reject,
                    weight=args.weight,
                    answer_id_context=last_ref.answer_id if last_ref else None,
                )
            )
        for event in events:
            api().append_feedback_event(event)
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{FAIL} feedback 저장 실패: {exc}", file=sys.stderr)
        return 2

    target_label = (
        f"last answer {last_ref.answer_id}"
        if args.feedback_target == "last" and last_ref
        else f"{args.feedback_target} {args.target_ref}"
    )
    print(
        f"{OK} Recorded {action} for {target_label} "
        f"(targets={len(events)}, weight={events[0].weight:+.2f})"
    )
    refs = ", ".join(event.target_ref for event in events)
    print(f"  → next index will apply updated feedback_score: {refs}")
    return 0


def _feedback_action(args: argparse.Namespace) -> str:
    actions = [
        bool(args.accept),
        bool(args.reject is not None),
        bool(args.weight is not None),
    ]
    if sum(actions) != 1:
        raise ValueError("exactly one of --accept, --reject, --weight is required")
    if args.accept:
        return "accept"
    if args.reject is not None:
        return "reject"
    return "weight"


def _feedback_targets(args: argparse.Namespace) -> list[object]:
    vault_path = Path(args.vault_path).expanduser() if args.vault_path else None
    if args.feedback_target == "last":
        last_ref = api().load_last_answer()
        if last_ref is None:
            raise ValueError("No recent answer found. Run ask/me first, then retry feedback last.")
        return api().resolve_last_answer_targets(last_ref)
    if args.feedback_target == "card":
        return [api().resolve_card_target(str(args.target_ref), vault_path=vault_path)]
    if args.feedback_target == "pattern":
        return [api().resolve_pattern_target(str(args.target_ref), vault_path=vault_path)]
    raise ValueError(f"unknown feedback target: {args.feedback_target}")


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("feedback", help="답변/Card/Pattern 피드백 기록")
    feedback_sub = parser.add_subparsers(
        dest="feedback_target",
        required=True,
        metavar="TARGET",
    )

    def add_action_args(target_parser: argparse.ArgumentParser) -> None:
        group = target_parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--accept", action="store_true", help="긍정 피드백")
        group.add_argument("--reject", help="부정 피드백 이유")
        group.add_argument("--weight", type=float, help="직접 가중치 delta (-1.0~1.0)")
        target_parser.add_argument("--vault-path", help="vault 경로 override")
        target_parser.set_defaults(func=cmd_feedback)

    last = feedback_sub.add_parser("last", help="직전 답변에 피드백")
    last.set_defaults(target_ref=None)
    add_action_args(last)

    card = feedback_sub.add_parser("card", help="특정 Card에 피드백")
    card.add_argument("target_ref", help="card id")
    add_action_args(card)

    pattern = feedback_sub.add_parser("pattern", help="특정 DecisionPattern에 피드백")
    pattern.add_argument("target_ref", help="pattern id")
    add_action_args(pattern)
