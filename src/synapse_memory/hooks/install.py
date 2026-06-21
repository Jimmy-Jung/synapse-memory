"""Install/uninstall Claude Code and Codex SessionStart hooks."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HOOK_COMMAND = "synapse-memory hook run --event session-start"
HOOK_ARGS = ("hook", "run", "--event", "session-start")
DEFAULT_TIMEOUT_SECONDS = 5
CODEX_SESSION_MATCHER = "startup|resume"
CODEX_STATUS_MESSAGE = "Loading Synapse Memory context"


@dataclass(frozen=True)
class HookDiagnostic:
    installed: bool
    message: str
    settings_path: Path
    ready: bool = False
    project_registered: bool = False
    cache_available: bool = False
    command_stable: bool = False


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
    command = build_hook_command()

    found, normalized = _normalize_synapse_hooks(session_hooks, command)
    if found and not normalized:
        return False

    _backup_if_exists(path)
    if not found:
        session_hooks.append(_claude_hook_group(command))
    _write_settings(path, settings)
    return True


def _install_codex_session_hook(codex_hooks_path: Path | None = None) -> bool:
    path = _codex_hooks_path(codex_hooks_path)
    settings = _load_settings(path)
    session_hooks = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
    command = build_hook_command()

    found, normalized = _normalize_synapse_hooks(session_hooks, command)
    if found and not normalized:
        return False

    _backup_if_exists(path)
    if not found:
        session_hooks.append(_codex_hook_group(command))
    _write_settings(path, settings)
    return True


def diagnose_session_hook(
    settings_path: Path | None = None,
    codex_hooks_path: Path | None = None,
    *,
    cwd: Path | None = None,
    synapse_home: Path | None = None,
) -> HookDiagnostic:
    """Claude Code/Codex SessionStart hook 설치 상태를 진단한다."""
    claude_path = _claude_settings_path(settings_path)
    codex_path = _codex_hooks_path(codex_hooks_path)
    home = _synapse_home(synapse_home)

    claude_installed, claude_message = _diagnose_hook_file(
        claude_path, label="Claude Code", missing_label="settings"
    )
    codex_installed, codex_message = _diagnose_hook_file(
        codex_path, label="Codex", missing_label="hooks"
    )
    installed = claude_installed and codex_installed
    project_registered = _is_project_registered(cwd or Path.cwd(), home)
    cache_available = _context_cache_path(home).is_file()
    command_stable = _hook_commands_are_stable(claude_path) and _hook_commands_are_stable(codex_path)
    ready = installed and project_registered and cache_available and command_stable

    status_messages = [claude_message, codex_message]
    if installed:
        status_messages.append(
            "현재 프로젝트 등록됨" if project_registered else "현재 프로젝트 미등록"
        )
        status_messages.append(
            f"context cache 있음: {_context_cache_path(home)}"
            if cache_available
            else f"context cache 없음: {_context_cache_path(home)}"
        )
        status_messages.append(
            "hook command 절대경로 OK"
            if command_stable
            else "hook command PATH 의존 또는 실행 파일 없음"
        )

    return HookDiagnostic(
        installed,
        "; ".join(status_messages),
        claude_path,
        ready=ready,
        project_registered=project_registered,
        cache_available=cache_available,
        command_stable=command_stable,
    )


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
            if not (
                isinstance(hook, dict)
                and _is_synapse_hook_command(hook.get("command"))
            )
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


def build_hook_command() -> str:
    """PATH가 좁은 app hook 환경에서도 실행되도록 executable을 절대경로화한다."""
    executable = _resolve_hook_executable()
    if executable is None:
        return HOOK_COMMAND
    return " ".join([shlex.quote(executable), *HOOK_ARGS])


def _resolve_hook_executable() -> str | None:
    env_value = os.environ.get("SYNAPSE_MEMORY_EXECUTABLE")
    candidates = [
        Path(env_value).expanduser() if env_value else None,
        Path.home() / ".local" / "bin" / "synapse-memory",
    ]
    found = shutil.which("synapse-memory")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    return None


def _claude_hook_group(command: str | None = None) -> dict[str, Any]:
    return {
        "hooks": [
            {
                "type": "command",
                "command": command or build_hook_command(),
                "timeout": DEFAULT_TIMEOUT_SECONDS,
            }
        ]
    }


def _codex_hook_group(command: str | None = None) -> dict[str, Any]:
    return {
        "matcher": CODEX_SESSION_MATCHER,
        "hooks": [
            {
                "type": "command",
                "command": command or build_hook_command(),
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
            if isinstance(hook, dict) and _is_synapse_hook_command(hook.get("command")):
                return True
    return False


def _normalize_synapse_hooks(session_hooks: list[Any], command: str) -> tuple[bool, bool]:
    found = False
    changed = False
    for group in session_hooks:
        if not isinstance(group, dict):
            continue
        group_hooks = group.get("hooks", [])
        if not isinstance(group_hooks, list):
            continue
        for hook in group_hooks:
            if not isinstance(hook, dict):
                continue
            if not _is_synapse_hook_command(hook.get("command")):
                continue
            found = True
            if hook.get("command") != command:
                hook["command"] = command
                changed = True
            if hook.get("timeout") != DEFAULT_TIMEOUT_SECONDS:
                hook["timeout"] = DEFAULT_TIMEOUT_SECONDS
                changed = True
    return found, changed


def _is_synapse_hook_command(command: object) -> bool:
    if not isinstance(command, str):
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) != 1 + len(HOOK_ARGS):
        return False
    executable = Path(parts[0]).name
    return executable == "synapse-memory" and tuple(parts[1:]) == HOOK_ARGS


def _hook_commands_are_stable(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        settings = _load_settings(path)
    except ValueError:
        return False
    hooks = settings.get("hooks")
    session_hooks = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    if not isinstance(session_hooks, list):
        return False
    stable_commands: list[bool] = []
    for group in session_hooks:
        if not isinstance(group, dict):
            continue
        group_hooks = group.get("hooks")
        if not isinstance(group_hooks, list):
            continue
        for hook in group_hooks:
            if not isinstance(hook, dict):
                continue
            command = hook.get("command")
            if _is_synapse_hook_command(command):
                stable_commands.append(_is_stable_command(command))
    return bool(stable_commands) and all(stable_commands)


def _is_stable_command(command: object) -> bool:
    if not isinstance(command, str):
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    executable = Path(parts[0]).expanduser()
    if not executable.is_absolute():
        return False
    return executable.is_file() and os.access(executable, os.X_OK)


def _synapse_home(path: Path | None = None) -> Path:
    return path or Path(os.environ.get("SYNAPSE_HOME", "~/.synapse")).expanduser()


def _context_cache_path(home: Path) -> Path:
    return home / "context" / "rendered.md"


def _is_project_registered(cwd: Path, home: Path) -> bool:
    try:
        data = json.loads((home / "projects.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    projects = data.get("projects")
    if not isinstance(projects, list):
        return False
    current = cwd.expanduser().resolve()
    for entry in projects:
        if not isinstance(entry, dict) or entry.get("state") != "active":
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        try:
            current.relative_to(Path(raw_path).expanduser().resolve())
            return True
        except (OSError, ValueError):
            continue
    return False
