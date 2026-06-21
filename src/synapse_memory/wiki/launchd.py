# src/synapse_memory/wiki/launchd.py
"""launchd LaunchAgent — StartInterval로 주기 실행되는 bounded 단명 사이클 (020).

상주 데몬 / 파일이벤트(WatchPaths) 대신 launchd가 N분마다 ``watch run``을 1회
띄우고, 그 프로세스는 bounded 작업 후 즉시 종료한다(프로세스 죽음 = 메모리 회수).
``_launchctl``이 유일한 subprocess seam이라 테스트는 이를 monkeypatch하고 실제
launchctl을 절대 호출하지 않는다. ``home=``으로 테스트 격리도 가능.

저자: Synapse Memory Maintainers
작성일: 2026-06-15 (020 갱신: 2026-06-16)
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

LABEL = "com.synapse-memory.watch"
DEFAULT_INTERVAL_SECONDS = 1200  # 20분 — config.maintenance.interval_minutes 폴백
_STANDARD_PATHS = ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")
_USER_BIN_SUFFIXES = ("bin", ".local/bin", ".cargo/bin", ".npm/bin", ".bun/bin")
_UNSTABLE_PATH_MARKERS = (
    "/.codex/tmp/",
    "/.venv/",
    "/node_modules/",
    "/private/tmp/",
    "/private/var/folders/",
    "/tmp/",
    "/var/tmp/",
)


class LaunchctlError(RuntimeError):
    """launchctl load/unload 실패."""


def _known_user_bin_paths() -> tuple[str, ...]:
    home = os.path.normpath(os.path.expanduser("~"))
    return tuple(os.path.join(home, suffix) for suffix in _USER_BIN_SUFFIXES)


def _is_persistent_path(path: str) -> bool:
    normalized = os.path.normpath(os.path.expanduser(path))
    if not os.path.isabs(normalized):
        return False
    return not any(marker in f"{normalized}/" for marker in _UNSTABLE_PATH_MARKERS)


def _daemon_path(program_args: list[str]) -> str:
    """launchd 기본 환경에서도 CLI 바이너리를 찾는 안정적인 PATH를 만든다."""
    parts: list[str] = []
    program = program_args[0] if program_args else ""
    if os.path.isabs(program):
        program_dir = os.path.dirname(program)
        if _is_persistent_path(program_dir):
            parts.append(program_dir)
    claude = shutil.which("claude")
    if claude:
        claude_dir = os.path.dirname(claude)
        if _is_persistent_path(claude_dir):
            parts.append(claude_dir)
    parts.extend(_known_user_bin_paths())
    parts.append("/opt/homebrew/bin")
    parts.extend(_STANDARD_PATHS)

    seen: set[str] = set()
    deduped: list[str] = []
    for part in parts:
        normalized = os.path.normpath(os.path.expanduser(part))
        if _is_persistent_path(normalized) and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return os.pathsep.join(deduped)


def build_plist(*, program_args: list[str], interval_seconds: int) -> str:
    """launchd plist XML 문자열 생성 — StartInterval 주기 실행.

    WatchPaths(파일이벤트, self-trigger 위험) 대신 StartInterval을 쓴다. 동일
    interval을 ThrottleInterval로도 걸어 사이클 중첩 실행을 막는다(락과 이중 방어).
    """
    payload = {
        "Label": LABEL,
        "ProgramArguments": list(program_args),
        "StartInterval": int(interval_seconds),
        "ThrottleInterval": int(interval_seconds),
        "RunAtLoad": False,
        "EnvironmentVariables": {"PATH": _daemon_path(program_args)},
        "StandardOutPath": str(l0_root() / "watch.out.log"),
        "StandardErrorPath": str(l0_root() / "watch.err.log"),
    }
    return plistlib.dumps(payload).decode("utf-8")


def plist_path(*, home: Path | None = None) -> Path:
    """LaunchAgent plist 경로 — ``~/Library/LaunchAgents/<LABEL>.plist``."""
    base = home if home is not None else Path.home()
    return base / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchctl(*args: str) -> None:
    """유일한 subprocess seam — 테스트는 이 함수를 monkeypatch한다."""
    result = subprocess.run(["launchctl", *args], check=False, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise LaunchctlError(
            f"launchctl {' '.join(args)} failed (rc={result.returncode}): {stderr}"
        )


def install_watch(
    *,
    home: Path | None = None,
    program_args: list[str] | None = None,
    interval_seconds: int | None = None,
) -> Path:
    """plist를 작성하고 launchctl로 로드. 작성된 plist 경로 반환.

    ``interval_seconds`` 미지정 시 ``config.maintenance.interval_minutes``(분)을
    초로 환산해 사용한다(해석 실패 시 ``DEFAULT_INTERVAL_SECONDS``).
    """
    if program_args is None:
        program_args = [
            shutil.which("synapse-memory") or "synapse-memory",
            "watch",
            "run",
        ]
    if interval_seconds is None:
        try:
            from synapse_memory.config import get_config

            interval_seconds = get_config().maintenance.interval_minutes * 60
        except Exception:
            interval_seconds = DEFAULT_INTERVAL_SECONDS
    path = plist_path(home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_plist(program_args=program_args, interval_seconds=interval_seconds),
        encoding="utf-8",
    )
    _launchctl("load", "-w", str(path))
    return path


def uninstall_watch(*, home: Path | None = None) -> None:
    """로드 해제 후 plist 제거."""
    path = plist_path(home=home)
    if path.exists():
        _launchctl("unload", str(path))
        path.unlink(missing_ok=True)
