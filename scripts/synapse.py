#!/usr/bin/env python3
"""
Unified CLI for the Synapse Memory plugin.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_archive_normalized as archive_mod
import synapse_bootstrap as bootstrap_mod
import synapse_config as config
import synapse_e2e_fixture as e2e_mod
import synapse_inbox_review as review_mod
import synapse_install_phase3 as install_mod
import synapse_kpi as kpi_mod
import synapse_reflect as reflect_mod
import obsidian_vault_setup as vault_setup_mod


def set_vault_env(path: Path | None) -> None:
    if path is not None:
        os.environ[config.ENV_VAULT_AI_ROOT] = str(path.expanduser())


def print_json(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = config.vault_ai_root(args.vault_ai_root)
    missing = config.validate_vault_ai_root(root)
    return print_json(
        {
            "plugin_root": str(config.PLUGIN_ROOT),
            "runtime_root": str(config.runtime_root()),
            "private_root": str(config.private_root()),
            "vault_ai_root": str(root),
            "vault_ready": not missing,
            "missing": missing,
        }
    )


def command_bootstrap(args: argparse.Namespace) -> int:
    result = bootstrap_mod.bootstrap(root=args.runtime_root, settings_file=args.settings, apply=args.apply)
    return print_json(result)


def command_install(args: argparse.Namespace) -> int:
    set_vault_env(args.vault_ai_root)
    result = install_mod.install_phase3(
        dry_run=not args.install,
        load_agents=args.load_agents,
        bin_dir=args.runtime_root / "bin",
        backup_dir=args.runtime_root / "private" / "backups",
        settings_path=args.settings,
        launch_agents_dir=args.launch_agents_dir,
    )
    return print_json(result)


def command_e2e(args: argparse.Namespace) -> int:
    result = e2e_mod.run_e2e_fixture(work_dir=args.work_dir, dry_run=args.dry_run)
    return print_json(result)


def command_review(args: argparse.Namespace) -> int:
    root = config.vault_ai_root(args.vault_ai_root)
    result = review_mod.review_inbox(
        inbox_dir=config.memory_inbox_dir(root),
        review_path=config.memory_review_path(root),
        dry_run=args.dry_run,
    )
    return print_json(result)


def command_reflect(args: argparse.Namespace) -> int:
    root = config.vault_ai_root(args.vault_ai_root)
    result = reflect_mod.reflect_candidate(
        args.candidate_id,
        inbox_dir=config.memory_inbox_dir(root),
        profile_path=config.profile_path(root),
        patterns_path=config.decision_patterns_path(root),
        registry_path=config.decision_quality_registry_path(root),
        apply=args.apply,
    )
    return print_json(result)


def command_kpi(args: argparse.Namespace) -> int:
    root = config.vault_ai_root(args.vault_ai_root)
    result = kpi_mod.append_kpi(
        counter_dir=args.runtime_root / "counters",
        review_path=config.memory_review_path(root),
        date_utc=args.date_utc,
        dry_run=args.dry_run,
    )
    return print_json(result)


def command_archive(args: argparse.Namespace) -> int:
    root = config.vault_ai_root(args.vault_ai_root)
    result = archive_mod.archive_normalized(
        normalized_dir=args.runtime_root / "private" / "normalized",
        review_path=config.memory_review_path(root),
        threshold_bytes=args.threshold_bytes,
        older_than_days=args.older_than_days,
        dry_run=args.dry_run,
    )
    return print_json(result)


def command_vault_setup(args: argparse.Namespace) -> int:
    if args.apply:
        result = vault_setup_mod.apply_setup(
            args.vault_root.expanduser(),
            with_ai_memory=args.with_ai_memory,
            author=args.author,
            overwrite=args.overwrite,
        )
    else:
        result = {
            **vault_setup_mod.plan(
                args.vault_root.expanduser(),
                with_ai_memory=args.with_ai_memory,
                author=args.author,
            ),
            "applied": False,
        }
    return print_json(result)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault-ai-root", type=Path, default=None, help="Path to shared 90_System/AI directory")
    parser.add_argument("--runtime-root", type=Path, default=config.runtime_root(), help="Local runtime root; default ~/.synapse")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synapse Memory plugin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status")
    add_common(p_status)
    p_status.set_defaults(func=command_status)

    p_bootstrap = sub.add_parser("bootstrap")
    p_bootstrap.add_argument("--runtime-root", type=Path, default=config.runtime_root())
    p_bootstrap.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    p_bootstrap.add_argument("--apply", action="store_true")
    p_bootstrap.set_defaults(func=command_bootstrap)

    p_install = sub.add_parser("install")
    add_common(p_install)
    p_install.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    p_install.add_argument("--launch-agents-dir", type=Path, default=Path.home() / "Library" / "LaunchAgents")
    p_install.add_argument("--install", action="store_true", help="write files; default dry-run")
    p_install.add_argument("--load-agents", action="store_true")
    p_install.set_defaults(func=command_install)

    p_e2e = sub.add_parser("e2e")
    p_e2e.add_argument("--work-dir", type=Path)
    p_e2e.add_argument("--dry-run", action="store_true")
    p_e2e.set_defaults(func=command_e2e)

    p_review = sub.add_parser("review")
    add_common(p_review)
    p_review.add_argument("--dry-run", action="store_true")
    p_review.set_defaults(func=command_review)

    p_reflect = sub.add_parser("reflect")
    add_common(p_reflect)
    p_reflect.add_argument("candidate_id")
    p_reflect.add_argument("--apply", action="store_true")
    p_reflect.set_defaults(func=command_reflect)

    p_kpi = sub.add_parser("kpi")
    add_common(p_kpi)
    p_kpi.add_argument("--date-utc")
    p_kpi.add_argument("--dry-run", action="store_true")
    p_kpi.set_defaults(func=command_kpi)

    p_archive = sub.add_parser("archive")
    add_common(p_archive)
    p_archive.add_argument("--threshold-bytes", type=int, default=archive_mod.DEFAULT_THRESHOLD_BYTES)
    p_archive.add_argument("--older-than-days", type=int, default=archive_mod.DEFAULT_OLDER_THAN_DAYS)
    p_archive.add_argument("--dry-run", action="store_true")
    p_archive.set_defaults(func=command_archive)

    p_vault = sub.add_parser("vault-setup")
    p_vault.add_argument("--vault-root", type=Path, required=True)
    p_vault.add_argument("--author", default="JunyoungJung")
    p_vault.add_argument("--with-ai-memory", action="store_true", default=True)
    p_vault.add_argument("--without-ai-memory", action="store_false", dest="with_ai_memory")
    p_vault.add_argument("--apply", action="store_true")
    p_vault.add_argument("--overwrite", action="store_true")
    p_vault.set_defaults(func=command_vault_setup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
