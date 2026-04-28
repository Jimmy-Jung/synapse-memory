#!/usr/bin/env python3
"""
Install Phase 3 hooks and LaunchAgent plist files.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE = SCRIPT_DIR / "synapse_pipeline.py"
LAUNCH_WRAPPER = SCRIPT_DIR / "synapse_launch_wrapper.py"
DEFAULT_PYTHON = Path(sys.executable)
DEFAULT_VAULT_AI_ROOT = Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "90_System" / "AI"
DEFAULT_BIN_DIR = Path.home() / ".synapse" / "bin"
DEFAULT_BACKUP_DIR = Path.home() / ".synapse" / "private" / "backups"
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"
DEFAULT_LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
DEFAULT_LOG_DIR = Path.home() / ".synapse" / "logs"

HOOK_LABEL = "net.synapse.claude-session-end"
HOOK_SCRIPT_NAME = "claude-session-end-hook.sh"
LAUNCH_AGENT_LABELS = (
    "net.synapse.collector",
    "net.synapse.codex-poller",
    "net.synapse.extractor",
    "net.synapse.reviewer",
)


class InstallError(Exception):
    """Raised when Phase 3 installation cannot be completed."""


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def atomic_write(path: Path, content: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_bytes(content)
    if mode is not None:
        tmp.chmod(mode)
    os.replace(tmp, path)


def build_hook_script(*, python_path: Path = DEFAULT_PYTHON, pipeline_path: Path = PIPELINE) -> str:
    return f"""#!/usr/bin/env bash
set -u
PYTHON_BIN="${{SYNAPSE_PYTHON:-{python_path}}}"
PIPELINE_SCRIPT="{pipeline_path}"
exec "$PYTHON_BIN" "$PIPELINE_SCRIPT" claude-session-end-hook
"""


def wrap_program_arguments(
    label: str,
    program_arguments: list[str],
    *,
    python_path: Path,
    wrapper_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> list[str]:
    return [
        str(python_path),
        str(wrapper_path),
        "--label",
        label,
        "--stdout-path",
        str(stdout_path),
        "--stderr-path",
        str(stderr_path),
        "--",
        *program_arguments,
    ]


def launch_agent_payload(label: str, program_arguments: list[str], *, start_interval: int | None = None, start_calendar_interval: dict[str, int] | None = None, throttle_interval: int | None = None, log_dir: Path = DEFAULT_LOG_DIR, python_path: Path = DEFAULT_PYTHON, wrapper_path: Path = LAUNCH_WRAPPER, vault_ai_root: Path = DEFAULT_VAULT_AI_ROOT) -> dict[str, Any]:
    stdout_path = log_dir / f"{label}.out.log"
    stderr_path = log_dir / f"{label}.err.log"
    payload: dict[str, Any] = {
        "Label": label,
        "ProgramArguments": wrap_program_arguments(
            label,
            program_arguments,
            python_path=python_path,
            wrapper_path=wrapper_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        ),
        "RunAtLoad": False,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "WorkingDirectory": str(SCRIPT_DIR.parent),
        "EnvironmentVariables": {
            "SYNAPSE_VAULT_AI_ROOT": str(vault_ai_root),
        },
    }
    if start_interval is not None:
        payload["StartInterval"] = start_interval
    if start_calendar_interval is not None:
        payload["StartCalendarInterval"] = start_calendar_interval
    if throttle_interval is not None:
        payload["ThrottleInterval"] = throttle_interval
    return payload


def build_launch_agents(*, python_path: Path = DEFAULT_PYTHON, pipeline_path: Path = PIPELINE, wrapper_path: Path = LAUNCH_WRAPPER, log_dir: Path = DEFAULT_LOG_DIR, vault_ai_root: Path = DEFAULT_VAULT_AI_ROOT) -> dict[str, dict[str, Any]]:
    return {
        "net.synapse.collector": launch_agent_payload(
            "net.synapse.collector",
            [str(python_path), str(pipeline_path), "collector"],
            start_interval=180,
            throttle_interval=60,
            log_dir=log_dir,
            python_path=python_path,
            wrapper_path=wrapper_path,
            vault_ai_root=vault_ai_root,
        ),
        "net.synapse.codex-poller": launch_agent_payload(
            "net.synapse.codex-poller",
            [str(python_path), str(pipeline_path), "codex-poller"],
            start_interval=180,
            throttle_interval=60,
            log_dir=log_dir,
            python_path=python_path,
            wrapper_path=wrapper_path,
            vault_ai_root=vault_ai_root,
        ),
        "net.synapse.extractor": launch_agent_payload(
            "net.synapse.extractor",
            [str(python_path), str(pipeline_path), "extractor"],
            start_calendar_interval={"Minute": 0},
            throttle_interval=60,
            log_dir=log_dir,
            python_path=python_path,
            wrapper_path=wrapper_path,
            vault_ai_root=vault_ai_root,
        ),
        "net.synapse.reviewer": launch_agent_payload(
            "net.synapse.reviewer",
            [str(python_path), str(pipeline_path), "reviewer"],
            start_calendar_interval={"Hour": 0, "Minute": 0},
            throttle_interval=60,
            log_dir=log_dir,
            python_path=python_path,
            wrapper_path=wrapper_path,
            vault_ai_root=vault_ai_root,
        ),
    }


def synapse_hook_entry(hook_script: Path) -> dict[str, Any]:
    return {
        "matcher": "logout|prompt_input_exit",
        "hooks": [
            {
                "type": "command",
                "command": str(hook_script),
                "async": True,
                "timeout": 5,
            }
        ],
    }


def patch_settings_data(settings: dict[str, Any], hook_script: Path) -> dict[str, Any]:
    patched = json.loads(json.dumps(settings))
    hooks = patched.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("settings.hooks must be an object")
    session_end = hooks.setdefault("SessionEnd", [])
    if not isinstance(session_end, list):
        raise InstallError("settings.hooks.SessionEnd must be a list")

    command = str(hook_script)
    for group in session_end:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []):
            if isinstance(hook, dict) and hook.get("command") == command:
                return patched

    session_end.append(synapse_hook_entry(hook_script))
    return patched


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InstallError(f"settings JSON must be an object: {path}")
    return data


def backup_settings(settings_path: Path, backup_dir: Path) -> Path | None:
    if not settings_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"settings.json.{utc_stamp()}.phase3"
    shutil.copy2(settings_path, backup)
    return backup


def write_launch_agents(plists: dict[str, dict[str, Any]], launch_agents_dir: Path) -> list[Path]:
    written: list[Path] = []
    for label, payload in plists.items():
        path = launch_agents_dir / f"{label}.plist"
        atomic_write(path, plistlib.dumps(payload, sort_keys=True), mode=0o644)
        written.append(path)
    return written


def bootstrap_launch_agents(paths: list[Path]) -> None:
    target = f"gui/{os.getuid()}"
    for path in paths:
        subprocess.run(["launchctl", "bootstrap", target, str(path)], check=False)


def install_phase3(
    *,
    dry_run: bool = True,
    load_agents: bool = False,
    bin_dir: Path = DEFAULT_BIN_DIR,
    settings_path: Path = DEFAULT_SETTINGS,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    launch_agents_dir: Path = DEFAULT_LAUNCH_AGENTS,
    python_path: Path = DEFAULT_PYTHON,
    pipeline_path: Path = PIPELINE,
    vault_ai_root: Path = DEFAULT_VAULT_AI_ROOT,
) -> dict[str, Any]:
    hook_script = bin_dir / HOOK_SCRIPT_NAME
    plists = build_launch_agents(python_path=python_path, pipeline_path=pipeline_path, vault_ai_root=vault_ai_root)
    settings = load_settings(settings_path)
    patched_settings = patch_settings_data(settings, hook_script)

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "hook_script": str(hook_script),
        "settings_path": str(settings_path),
        "vault_ai_root": str(vault_ai_root),
        "launch_agents": [str(launch_agents_dir / f"{label}.plist") for label in plists],
        "settings_changed": patched_settings != settings,
        "loaded": False,
    }
    if dry_run:
        return summary

    backup = backup_settings(settings_path, backup_dir)
    summary["settings_backup"] = str(backup) if backup else None

    atomic_write(hook_script, build_hook_script(python_path=python_path, pipeline_path=pipeline_path).encode("utf-8"), mode=0o755)
    settings_bytes = json.dumps(patched_settings, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write(settings_path, settings_bytes, mode=0o644)
    written_plists = write_launch_agents(plists, launch_agents_dir)
    if load_agents:
        bootstrap_launch_agents(written_plists)
        summary["loaded"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Synapse Phase 3 hooks and LaunchAgents")
    parser.add_argument("--install", action="store_true", help="write files; default is dry-run")
    parser.add_argument("--load-agents", action="store_true", help="launchctl bootstrap generated LaunchAgents")
    args = parser.parse_args(argv)

    result = install_phase3(dry_run=not args.install, load_agents=args.load_agents)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
