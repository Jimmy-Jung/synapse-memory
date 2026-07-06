"""setup, sync, and context commands."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import sys
from pathlib import Path

from synapse_memory.cli.common import FAIL, OK, api


def _setup_registry_path() -> Path:
    return Path.home() / ".synapse" / "projects.yaml"


def _setup_profile_patterns_paths(vault: Path) -> tuple[Path, Path]:
    from synapse_memory.profile.wiki import profile_page_path

    profile = profile_page_path(vault)
    return profile, profile


def _hook_runtime_settings() -> tuple[bool, bool, int]:
    from synapse_memory.config import get_config

    hook = get_config(refresh=True).hook
    return hook.enabled, hook.suggest_register, hook.max_inject_bytes


def _render_hook_settings_cache(*, max_inject_bytes: int | None = None) -> Path:
    from synapse_memory.projects.summary import render_hook_settings_cache

    enabled, suggest_register, configured_max = api()._hook_runtime_settings()
    return render_hook_settings_cache(
        enabled=enabled,
        suggest_register=suggest_register,
        max_inject_bytes=max_inject_bytes or configured_max,
    )


def cmd_setup(args: argparse.Namespace) -> int:
    from synapse_memory.projects.marker import MarkerParseError, inject_or_replace
    from synapse_memory.projects.registry import (
        ProjectEntry,
        load_registry,
        save_registry,
        upsert_entry,
    )
    from synapse_memory.projects.summary import generate_marker_body, render_context_cache

    vault = api()._resolve_vault(require_exists=True)
    profile, patterns = api()._setup_profile_patterns_paths(vault)
    body = generate_marker_body(profile, patterns)
    _, _, max_inject_bytes = api()._hook_runtime_settings()

    project = Path.cwd().resolve()
    setup_target = args.target or "hook"
    targets_for = {
        "codex": ["AGENTS.md"],
        "agents": ["AGENTS.md"],
        "claude": ["CLAUDE.md"],
        "both": ["AGENTS.md", "CLAUDE.md"],
        "hook": [],
    }[setup_target]

    if args.dry_run:
        print(f"[dry-run] project: {project}")
        if not targets_for:
            print("  marker: 생성/갱신 안 함 (hook 등록만)")
        for name in targets_for:
            target_file = project / name
            status = "신규 생성" if not target_file.is_file() else "갱신"
            print(f"  {status}: {target_file}")
        print(f"  registry: {api()._setup_registry_path()} (등록 예정, target={setup_target})")
        return 0

    for name in targets_for:
        target_file = project / name
        try:
            changed, _ = inject_or_replace(target_file, body)
        except MarkerParseError as exc:
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        action = "변경됨" if changed else "동일"
        print(f"  {OK} {target_file} — {action}")

    registry = api()._setup_registry_path()
    entries = load_registry(registry)
    new = ProjectEntry(
        path=project,
        target=setup_target,
        registered_at=datetime.date.today(),
        last_sync=None,
        state="active",
    )
    entries = upsert_entry(entries, new)
    save_registry(entries, registry)
    render_context_cache(profile, patterns, max_bytes=max_inject_bytes)
    api()._render_hook_settings_cache(max_inject_bytes=max_inject_bytes)
    print(f"  {OK} registry: {registry}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    from synapse_memory.projects.marker import MarkerParseError, inject_or_replace
    from synapse_memory.projects.registry import (
        ProjectEntry,
        load_registry,
        mark_stale,
        save_registry,
    )
    from synapse_memory.projects.summary import generate_marker_body, render_context_cache

    vault = api()._resolve_vault(require_exists=True)
    profile, patterns = api()._setup_profile_patterns_paths(vault)
    body = generate_marker_body(profile, patterns)
    _, _, max_inject_bytes = api()._hook_runtime_settings()

    registry = api()._setup_registry_path()
    entries = load_registry(registry)
    if not entries:
        print("등록된 프로젝트가 없습니다. `synapse-memory setup` 먼저 실행하세요.")
        return 0

    if args.current:
        cwd = Path.cwd().resolve()
        entries_to_sync = [entry for entry in entries if entry.path == cwd]
        if not entries_to_sync:
            print(f"{FAIL} 현재 디렉터리가 registry에 없습니다: {cwd}", file=sys.stderr)
            return 2
    else:
        entries_to_sync = list(entries)

    today = datetime.date.today()
    new_entries = list(entries)
    for entry in entries_to_sync:
        if not entry.path.is_dir():
            new_entries = mark_stale(new_entries, entry.path)
            print(f"  ⚠ stale: {entry.path}", file=sys.stderr)
            continue
        targets_for = {
            "codex": ["AGENTS.md"],
            "agents": ["AGENTS.md"],
            "claude": ["CLAUDE.md"],
            "both": ["AGENTS.md", "CLAUDE.md"],
            "hook": [],
        }[entry.target]
        for name in targets_for:
            try:
                inject_or_replace(entry.path / name, body)
            except MarkerParseError as exc:
                print(f"{FAIL} {exc}", file=sys.stderr)
                return 1
        new_entries = [
            ProjectEntry(
                path=item.path,
                target=item.target,
                registered_at=item.registered_at,
                last_sync=today if item.path == entry.path else item.last_sync,
                state=item.state,
            )
            for item in new_entries
        ]
        print(f"  {OK} sync: {entry.path}")

    save_registry(new_entries, registry)
    cache = render_context_cache(profile, patterns, max_bytes=max_inject_bytes)
    api()._render_hook_settings_cache(max_inject_bytes=max_inject_bytes)
    print(f"  {OK} context-cache: {cache}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    if args.action == "render":
        from synapse_memory.projects.summary import render_context_cache

        vault = api()._resolve_vault(require_exists=True)
        profile, patterns = api()._setup_profile_patterns_paths(vault)
        out_path = Path(args.out).expanduser().resolve() if args.out else None
        _, _, configured_max = api()._hook_runtime_settings()
        max_bytes = args.max_bytes if args.max_bytes is not None else configured_max
        cache = render_context_cache(
            profile,
            patterns,
            out_path=out_path,
            max_bytes=max_bytes,
        )
        api()._render_hook_settings_cache(max_inject_bytes=max_bytes)
        print(f"{OK} context-cache: {cache}")
        return 0

    print(f"{FAIL} unknown context action: {args.action}", file=sys.stderr)
    return 2


def _refresh_hook_sidecars() -> None:
    with contextlib.suppress(Exception):
        from synapse_memory.projects.registry import load_registry, save_registry

        registry = api()._setup_registry_path()
        if registry.is_file():
            save_registry(load_registry(registry), registry)

    with contextlib.suppress(Exception):
        from synapse_memory.projects.summary import render_context_cache

        vault = api()._resolve_vault(require_exists=True)
        profile, patterns = api()._setup_profile_patterns_paths(vault)
        _, _, max_inject_bytes = api()._hook_runtime_settings()
        render_context_cache(profile, patterns, max_bytes=max_inject_bytes)
        api()._render_hook_settings_cache(max_inject_bytes=max_inject_bytes)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup = subparsers.add_parser("setup", help="현재 디렉터리를 hook 주입 대상으로 등록")
    setup.add_argument(
        "--target",
        choices=("agents", "claude", "both", "codex"),
        default=None,
        help="marker를 삽입할 대상 파일 (미지정 시 파일 수정 없이 hook 등록)",
    )
    setup.add_argument("--dry-run", action="store_true")
    setup.set_defaults(func=cmd_setup)

    sync = subparsers.add_parser(
        "sync",
        help="등록된 모든 프로젝트의 SYNAPSE-MEMORY marker 갱신",
    )
    sync.add_argument("--current", action="store_true", help="cwd 프로젝트만 갱신")
    sync.set_defaults(func=cmd_sync)

    context = subparsers.add_parser("context", help="hook context cache 관리")
    context_sub = context.add_subparsers(dest="action", required=True, metavar="ACTION")
    render = context_sub.add_parser("render", help="Profile/DecisionPatterns hook cache 렌더")
    render.add_argument("--out", default=None)
    render.add_argument("--max-bytes", type=int, default=None)
    render.set_defaults(func=cmd_context)
