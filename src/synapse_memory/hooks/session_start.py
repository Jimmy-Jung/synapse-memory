"""SessionStart hook — 등록 프로젝트에 컨텍스트 주입.

제약: stdlib만 사용. 실패는 세션 시작을 막지 않도록 모두 침묵 처리한다.

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

MAX_BYTES = 2048
FALLBACK = "Synapse Memory: 컨텍스트 캐시 없음 — `synapse-memory sync` 실행으로 생성 가능."
SUGGEST_REGISTER = (
    "Synapse Memory: 이 프로젝트는 미등록입니다. "
    "`synapse-memory setup --no-marker`로 등록하면 다음 세션부터 컨텍스트가 주입됩니다."
)


def main() -> int:
    try:
        settings = _read_hook_settings()
        if settings.get("enabled") is False:
            return 0
        cwd = Path.cwd().resolve()
        if _registered_root(cwd) is None:
            if _should_suggest_register(cwd, settings):
                sys.stdout.write(SUGGEST_REGISTER)
            return 0
        body = _read_rendered_context(settings)
        sys.stdout.write(body)
        return 0
    except Exception:
        return 0


def _registered_root(cwd: Path) -> str | None:
    try:
        data = json.loads(_registry_json_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    projects = data.get("projects", [])
    if not isinstance(projects, list):
        return None

    for entry in projects:
        if not isinstance(entry, dict):
            continue
        if entry.get("state") != "active":
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        root = Path(raw_path).expanduser()
        if _is_relative_to(cwd, root):
            return str(root)
    return None


def _read_rendered_context(settings: dict[str, object]) -> str:
    try:
        raw = _rendered_context_path().read_bytes()[:_max_inject_bytes(settings)]
    except OSError:
        return FALLBACK
    return raw.decode("utf-8", errors="ignore")


def _should_suggest_register(cwd: Path, settings: dict[str, object]) -> bool:
    env_value = os.environ.get("SYNAPSE_HOOK_SUGGEST_REGISTER")
    if env_value is not None:
        suggest_enabled = env_value.lower() in {
            "1",
            "true",
            "yes",
        }
    else:
        suggest_enabled = settings.get("suggest_register") is True
    if not suggest_enabled:
        return False
    if not _is_git_repo(cwd):
        return False

    sentinel = _suggestion_sentinel_path(cwd)
    try:
        if sentinel.exists():
            return False
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("", encoding="utf-8")
        return True
    except OSError:
        return False


def _read_hook_settings() -> dict[str, object]:
    try:
        data = json.loads(_hook_settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    hook = data.get("hook")
    return hook if isinstance(hook, dict) else {}


def _max_inject_bytes(settings: dict[str, object]) -> int:
    value = settings.get("max_inject_bytes")
    if isinstance(value, int) and value > 0:
        return value
    return MAX_BYTES


def _is_git_repo(path: Path) -> bool:
    current = path
    while True:
        if (current / ".git").exists():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _suggestion_sentinel_path(cwd: Path) -> Path:
    digest = hashlib.sha256(str(cwd).encode("utf-8")).hexdigest()[:16]
    return _synapse_home() / "context" / "suggested" / f"{digest}.sentinel"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


def _synapse_home() -> Path:
    return Path(os.environ.get("SYNAPSE_HOME", "~/.synapse")).expanduser()


def _registry_json_path() -> Path:
    return _synapse_home() / "projects.json"


def _rendered_context_path() -> Path:
    return _synapse_home() / "context" / "rendered.md"


def _hook_settings_path() -> Path:
    return _synapse_home() / "context" / "settings.json"


if __name__ == "__main__":
    raise SystemExit(main())
