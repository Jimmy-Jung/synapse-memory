"""profile control-plane commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import ModuleType
from typing import cast

from synapse_memory.cli.common import api


def _profile_ops() -> ModuleType:
    from synapse_memory.profile import control_plane

    return control_plane


def _resolve_existing(args: argparse.Namespace | None = None) -> Path:
    return cast(Path, api()._resolve_vault(args, require_exists=True))


def cmd_list_pending_profiles(args: argparse.Namespace) -> int:
    return cast(int, _profile_ops().list_pending_profiles(args, resolve_vault=_resolve_existing))


def cmd_dismiss_profile(args: argparse.Namespace) -> int:
    return cast(int, _profile_ops().dismiss_profile(args, resolve_vault=_resolve_existing))


def cmd_dismiss_list(args: argparse.Namespace) -> int:
    return cast(int, _profile_ops().dismiss_list(args, resolve_vault=_resolve_existing))


def cmd_dismiss_purge_expired(args: argparse.Namespace) -> int:
    return cast(int, _profile_ops().dismiss_purge_expired(args, resolve_vault=_resolve_existing))


def cmd_ledger_show(args: argparse.Namespace) -> int:
    return cast(int, _profile_ops().ledger_show(args))


def cmd_profile_review_awaiting(args: argparse.Namespace) -> int:
    return cast(int, _profile_ops().review_awaiting(args, resolve_vault=_resolve_existing))


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pending = subparsers.add_parser(
        "list-pending-profiles",
        help="vault MemoryInbox의 status=pending_review 후보 파일 목록",
    )
    pending.add_argument("--vault", default=None)
    pending.add_argument("--json", action="store_true")
    pending.set_defaults(func=cmd_list_pending_profiles)

    dismiss = subparsers.add_parser(
        "dismiss-profile",
        help="ProfileFact/DecisionPattern 후보를 dismissed 목록에 추가",
    )
    dismiss.add_argument("--kind", choices=("fact", "pattern"), required=True)
    dismiss.add_argument("--text", required=True)
    dismiss.add_argument(
        "--reason",
        default="",
        choices=("", "one_time", "misclassified", "user_changed", "irrelevant", "other"),
    )
    dismiss.add_argument("--note", default="")
    dismiss.add_argument("--vault", default=None)
    dismiss.set_defaults(func=cmd_dismiss_profile)

    dismiss_list = subparsers.add_parser("dismiss-list", help="dismissed 목록 조회")
    dismiss_list.add_argument("--kind", choices=("fact", "pattern", "all"), default="all")
    dismiss_list.add_argument(
        "--reason",
        default=None,
        choices=("", "one_time", "misclassified", "user_changed", "irrelevant", "other"),
    )
    dismiss_list.add_argument("--active-only", action="store_true")
    dismiss_list.add_argument("--json", action="store_true")
    dismiss_list.add_argument("--vault", default=None)
    dismiss_list.set_defaults(func=cmd_dismiss_list)

    purge = subparsers.add_parser(
        "dismiss-purge-expired",
        help="TTL 만료된 dismissed 라인을 물리적으로 제거 (백업 후)",
    )
    purge.add_argument("--dry-run", action="store_true")
    purge.add_argument("--apply", action="store_true")
    purge.add_argument("--vault", default=None)
    purge.set_defaults(func=cmd_dismiss_purge_expired)

    ledger = subparsers.add_parser("ledger-show", help="profile_ledger.jsonl 조회")
    ledger.add_argument("--kind", choices=("fact", "pattern", "all"), default="all")
    ledger.add_argument(
        "--status",
        choices=("all", "promoted", "awaiting"),
        default="all",
    )
    ledger.add_argument("--top", type=int, default=20)
    ledger.add_argument("--json", action="store_true")
    ledger.set_defaults(func=cmd_ledger_show)

    review = subparsers.add_parser(
        "profile-review-awaiting",
        help="ledger awaiting 중 peak ≥ --min-confidence 인 항목을 promote",
    )
    review.add_argument("--min-confidence", type=float, default=0.85)
    review.add_argument("--dry-run", action="store_true")
    review.set_defaults(func=cmd_profile_review_awaiting)
