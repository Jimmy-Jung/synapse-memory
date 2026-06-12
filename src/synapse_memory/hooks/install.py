"""Install/uninstall Claude Code and Codex SessionStart hooks."""

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
CODEX_SESSION_MATCHER = "startup|resume"
CODEX_STATUS_MESSAGE = "Loading Synapse Memory context"


@dataclass(frozen=True)
class HookDiagnostic:
    installed: bool
    message: str
    settings_path: Path


def install_session_hook(
    settings_path: Path | None = None,
    codex_hooks_path: Path | None = None,
) -> bool:
    """Claude Code/Codex SessionStart hook을 멱등 등록한다."""
    return install_session_hooks(
        settings_path=settings_path,
        codex_hooks_path=codex_hooks_path,
    )


def install_session_hooks(
    settings_path: Path | None = None,
    codex_hooks_path: Path | None = None,
) -> bool:
    """Claude Code settings.json과 Codex hooks.json에 SessionStart hook을 등록한다."""
    claude_changed = _install_claude_session_hook(settings_path)
    codex_changed = _install_codex_session_hook(codex_hooks_path)
    return claude_changed or codex_changed


def _install_claude_session_hook(settings_path: Path | None = None) -> bool:
    path = _claude_settings_path(settings_path)
    settings = _load_settings(path)
    session_hooks = settings.setdefault("hooks", {}).setdefault("SessionStart", [])

    if _contains_synapse_hook(session_hooks):
        return False

    _backup_if_exists(path)
    session_hooks.append(_claude_hook_group())
    _write_settings(path, settings)
    return True


def _install_codex_session_hook(codex_hooks_path: Path | None = None) -> bool:
    path = _codex_hooks_path(codex_hooks_path)
    settings = _load_settings(path)
    session_hooks = settings.setdefault("hooks", {}).setdefault("SessionStart", [])

    if _contains_synapse_hook(session_hooks):
        return False

    _backup_if_exists(path)
    session_hooks.append(_codex_hook_group())
    _write_settings(path, settings)
    return True


def diagnose_session_hook(
    settings_path: Path | None = None,
    codex_hooks_path: Path | None = None,
) -> HookDiagnostic:
    """Claude Code/Codex SessionStart hook 설치 상태를 진단한다."""
    claude_path = _claude_settings_path(settings_path)
    codex_path = _codex_hooks_path(codex_hooks_path)

    claude_installed, claude_message = _diagnose_hook_file(
        claude_path, label="Claude Code", missing_label="settings"
    )
    codex_installed, codex_message = _diagnose_hook_file(
        codex_path, label="Codex", missing_label="hooks"
    )
    installed = claude_installed and codex_installed
    return HookDiagnostic(installed, f"{claude_message}; {codex_message}", claude_path)


def _diagnose_hook_file(
    path: Path,
    *,
    label: str,
    missing_label: str,
) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"{label} SessionStart hook 미설치 ({missing_label}: {path})"

    try:
        settings = _load_settings(path)
    except ValueError as exc:
        return False, f"{label} hook 진단 실패: {exc}"

    hooks = settings.get("hooks")
    session_hooks = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    installed = isinstance(session_hooks, list) and _contains_synapse_hook(session_hooks)
    if installed:
        return True, f"{label} SessionStart hook 설치됨: {path}"
    return False, f"{label} SessionStart hook 미설치: {path}"


def uninstall_session_hook(
    settings_path: Path | None = None,
    codex_hooks_path: Path | None = None,
) -> bool:
    """Claude Code/Codex hook 파일에서 Synapse hook entry만 제거한다."""
    claude_changed = _uninstall_session_hook_file(_claude_settings_path(settings_path))
    codex_changed = _uninstall_session_hook_file(_codex_hooks_path(codex_hooks_path))
    return claude_changed or codex_changed


def _uninstall_session_hook_file(path: Path) -> bool:
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


def _claude_settings_path(settings_path: Path | None = None) -> Path:
    return settings_path or Path.home() / ".claude" / "settings.json"


def _codex_hooks_path(codex_hooks_path: Path | None = None) -> Path:
    return codex_hooks_path or Path.home() / ".codex" / "hooks.json"


def _claude_hook_group() -> dict[str, Any]:
    return {
        "hooks": [
            {
                "type": "command",
                "command": HOOK_COMMAND,
                "timeout": DEFAULT_TIMEOUT_SECONDS,
            }
        ]
    }


def _codex_hook_group() -> dict[str, Any]:
    return {
        "matcher": CODEX_SESSION_MATCHER,
        "hooks": [
            {
                "type": "command",
                "command": HOOK_COMMAND,
                "timeout": DEFAULT_TIMEOUT_SECONDS,
                "statusMessage": CODEX_STATUS_MESSAGE,
            }
        ],
    }


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
