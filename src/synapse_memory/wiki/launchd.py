# src/synapse_memory/wiki/launchd.py
"""launchd LaunchAgent — StartInterval로 주기 실행되는 bounded 단명 사이클 (020).

상주 데몬 / 파일이벤트(WatchPaths) 대신 launchd가 N분마다 ``watch run``을 1회
띄우고, 그 프로세스는 bounded 작업 후 즉시 종료한다(프로세스 죽음 = 메모리 회수).
``_launchctl``이 유일한 subprocess seam이라 테스트는 이를 monkeypatch하고 실제
launchctl을 절대 호출하지 않는다. ``home=``으로 테스트 격리도 가능.

저자: Synapse Memory Maintainers
작성일: 2026-06-15 (020 갱신: 2026-06-16, 로그 경로 분리: 2026-10-19)
"""
from __future__ import annotations

import contextlib
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

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
# 외장 볼륨 마운트 루트. 테스트 seam — conftest가 가짜 루트로 교체한다.
_EXTERNAL_VOLUMES_ROOT = Path("/Volumes")


class LaunchctlError(RuntimeError):
    """launchctl load/unload 실패."""


def default_log_dir(*, home: Path | None = None) -> Path:
    """watch 로그 기본 디렉터리 — ``~/.synapse/logs`` (내장 디스크)."""
    base = home if home is not None else Path.home()
    return base / ".synapse" / "logs"


def configured_log_dir() -> Path:
    """``config.maintenance.log_dir`` — 미설정·해석 실패 시 기본 디렉터리."""
    try:
        from synapse_memory.config import get_config

        configured = get_config().maintenance.log_dir
    except Exception:
        configured = None
    return Path(configured) if configured else default_log_dir()


def check_log_dir(path: Path) -> Path:
    """launchd가 직접 열 수 있는 로그 디렉터리인지 확인하고 절대 경로를 반환.

    StandardOutPath/StandardErrorPath는 잡 프로세스가 아니라 launchd가 연다.
    외장 볼륨 경로면 launchd가 파일을 못 열어 잡이 EX_CONFIG(78)로 시작조차
    못 한다(프로그램 자체는 외장 볼륨 접근 가능 — 실측 2026-10-19).
    """
    resolved = Path(path).expanduser().resolve()
    # ponytail: /Volumes 하위 = 외장 휴리스틱 — 내장 보조 볼륨도 거부됨. 필요해지면 statfs 기반 판별로 교체.
    if resolved.is_relative_to(_EXTERNAL_VOLUMES_ROOT):
        raise ValueError(
            f"watch 로그 경로는 내장 디스크여야 합니다: {resolved}\n"
            "    외장 볼륨은 launchd가 로그 파일을 열지 못해 EX_CONFIG(78)로 잡이 시작되지 않습니다."
        )
    return resolved


def installed_err_log(*, home: Path | None = None) -> Path | None:
    """설치된 plist의 StandardErrorPath — plist 없음·파싱 실패 시 None."""
    try:
        payload = plistlib.loads(plist_path(home=home).read_bytes())
    except Exception:
        return None
    value = payload.get("StandardErrorPath") if isinstance(payload, dict) else None
    return Path(value) if value else None


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
    # engine CLI(claude/codex)는 nvm/brew 등 비표준 경로에 설치될 수 있어 install
    # 시점에 실제 위치를 해석해 PATH에 넣는다. 누락 시 데몬이 CLI를 못 찾아
    # AIUnavailableError로 전 doc 실패(pages=0).
    for cli_name in ("claude", "codex"):
        resolved = shutil.which(cli_name)
        if resolved:
            cli_dir = os.path.dirname(resolved)
            if _is_persistent_path(cli_dir):
                parts.append(cli_dir)
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


def build_plist(
    *, program_args: list[str], interval_seconds: int, log_dir: Path | None = None
) -> str:
    """launchd plist XML 문자열 생성 — StartInterval 주기 실행.

    WatchPaths(파일이벤트, self-trigger 위험) 대신 StartInterval을 쓴다. 동일
    interval을 ThrottleInterval로도 걸어 사이클 중첩 실행을 막는다(락과 이중 방어).
    로그는 L0(``~/.synapse/private``)가 아닌 ``log_dir``에 둔다 — L0는 외장 볼륨으로
    옮겨질 수 있고, 그러면 launchd가 로그 파일을 열지 못한다.
    """
    log_dir = log_dir or default_log_dir()
    payload = {
        "Label": LABEL,
        "ProgramArguments": list(program_args),
        "StartInterval": int(interval_seconds),
        "ThrottleInterval": int(interval_seconds),
        "RunAtLoad": False,
        "EnvironmentVariables": {"PATH": _daemon_path(program_args)},
        "StandardOutPath": str(log_dir / "watch.out.log"),
        "StandardErrorPath": str(log_dir / "watch.err.log"),
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
    log_dir: Path | None = None,
) -> Path:
    """plist를 작성하고 launchctl로 로드. 작성된 plist 경로 반환.

    ``interval_seconds`` 미지정 시 ``config.maintenance.interval_minutes``(분)을
    초로 환산해 사용한다(해석 실패 시 ``DEFAULT_INTERVAL_SECONDS``).
    ``log_dir`` 미지정 시 ``config.maintenance.log_dir``(없으면 ``~/.synapse/logs``).
    외장 볼륨 경로면 ``ValueError``.
    """
    log_dir = check_log_dir(log_dir if log_dir is not None else configured_log_dir())
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
    log_dir.mkdir(parents=True, exist_ok=True)  # launchd는 로그 디렉터리를 만들지 않는다
    path = plist_path(home=home)
    if path.exists():
        # 재설치 — 기존 잡을 내려야 새 plist(로그 경로·주기)가 반영된다.
        with contextlib.suppress(LaunchctlError):
            _launchctl("unload", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_plist(
            program_args=program_args,
            interval_seconds=interval_seconds,
            log_dir=log_dir,
        ),
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
