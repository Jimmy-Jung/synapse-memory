"""Install/uninstall Claude Code SessionStart hook."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HOOK_COMMAND = "synapse-memory hook run --event session-start"
DEFAULT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class HookDiagnostic:
    installed: bool
    message: str
    settings_path: Path


def install_session_hook(settings_path: Path | None = None) -> bool:
    """Claude Code settings.json에 SessionStart hook을 멱등 등록한다."""
    path = settings_path or Path.home() / ".claude" / "settings.json"
    settings = _load_settings(path)
    session_hooks = settings.setdefault("hooks", {}).setdefault("SessionStart", [])

    if _contains_synapse_hook(session_hooks):
        return False

    _backup_if_exists(path)
    session_hooks.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": HOOK_COMMAND,
                    "timeout": DEFAULT_TIMEOUT_SECONDS,
                }
            ]
        }
    )
    _write_settings(path, settings)
    return True


def diagnose_session_hook(settings_path: Path | None = None) -> HookDiagnostic:
    """Claude Code SessionStart hook 설치 상태를 진단한다."""
    path = settings_path or Path.home() / ".claude" / "settings.json"
    if not path.is_file():
        return HookDiagnostic(False, f"Claude Code SessionStart hook 미설치: {path}", path)

    try:
        settings = _load_settings(path)
    except ValueError as exc:
        return HookDiagnostic(False, f"Claude Code settings 진단 실패: {exc}", path)

    hooks = settings.get("hooks")
    session_hooks = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    installed = isinstance(session_hooks, list) and _contains_synapse_hook(session_hooks)
    if installed:
        return HookDiagnostic(True, f"Claude Code SessionStart hook 설치됨: {path}", path)
    return HookDiagnostic(False, f"Claude Code SessionStart hook 미설치: {path}", path)


def uninstall_session_hook(settings_path: Path | None = None) -> bool:
    """Claude Code settings.json에서 Synapse hook entry만 제거한다."""
    path = settings_path or Path.home() / ".claude" / "settings.json"
    if not path.is_file():
        return False

    settings = _load_settings(path)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    session_hooks = hooks.get("SessionStart")
    if not isinstance(session_hooks, list):
        return False

    changed = False
    kept_groups: list[Any] = []
    for group in session_hooks:
        if not isinstance(group, dict):
            kept_groups.append(group)
            continue
        group_hooks = group.get("hooks")
        if not isinstance(group_hooks, list):
            kept_groups.append(group)
            continue
        kept_hooks = [
            hook
            for hook in group_hooks
            if not (isinstance(hook, dict) and hook.get("command") == HOOK_COMMAND)
        ]
        if len(kept_hooks) != len(group_hooks):
            changed = True
        if kept_hooks:
            new_group = dict(group)
            new_group["hooks"] = kept_hooks
            kept_groups.append(new_group)

    if not changed:
        return False

    _backup_if_exists(path)
    hooks["SessionStart"] = kept_groups
    _write_settings(path, settings)
    return True


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"settings.json 파싱 실패: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"settings.json 루트가 object가 아님: {path}")
    return data


def _write_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix="settings-", suffix=".json.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), 0o600)
            fh.write(serialized)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _backup_if_exists(path: Path) -> None:
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)


def _contains_synapse_hook(session_hooks: list[Any]) -> bool:
    for group in session_hooks:
        if not isinstance(group, dict):
            continue
        group_hooks = group.get("hooks", [])
        if not isinstance(group_hooks, list):
            continue
        for hook in group_hooks:
            if isinstance(hook, dict) and hook.get("command") == HOOK_COMMAND:
                return True
    return False
