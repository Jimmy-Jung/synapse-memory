# src/synapse_memory/wiki/launchd.py
"""launchd LaunchAgent — raw 디렉터리 변화(WatchPaths/FSEvents) 시 watch 사이클 실행.

상주 데몬 대신 launchd가 변화 시 1회 실행. ``_launchctl``이 유일한 subprocess
seam이라 테스트는 이를 monkeypatch하고 실제 launchctl을 절대 호출하지 않는다.
``home=``을 받아 테스트 격리(임시 ``Library/LaunchAgents``)도 가능하다.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

LABEL = "com.synapse-memory.watch"


def build_plist(*, program_args: list[str], watch_paths: list[str]) -> str:
    """launchd plist XML 문자열 생성."""
    payload = {
        "Label": LABEL,
        "ProgramArguments": list(program_args),
        "WatchPaths": list(watch_paths),
        "RunAtLoad": False,
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
    subprocess.run(["launchctl", *args], check=False, capture_output=True)


def install_watch(
    *,
    home: Path | None = None,
    program_args: list[str] | None = None,
    watch_paths: list[str] | None = None,
) -> Path:
    """plist를 작성하고 launchctl로 로드. 작성된 plist 경로 반환."""
    if program_args is None:
        program_args = [
            shutil.which("synapse-memory") or "synapse-memory",
            "watch",
            "run",
        ]
    if watch_paths is None:
        watch_paths = [str(l0_root() / "raw" / "claude-code")]
    path = plist_path(home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_plist(program_args=program_args, watch_paths=watch_paths),
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
