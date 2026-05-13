"""L0 (raw) 저장소 관리.

원칙
----
- 위치: ``~/.synapse/private/`` (사용자 홈, vault 외부, iCloud sync 제외)
- 디렉토리 권한: 0700 (소유자 전용)
- 파일 권한: 0600
- 외부 LLM(Claude/GPT 등)에 절대 노출 금지 — 모든 cloud 호출은 redacted L1 이후만
- vault CLAUDE.md 원칙: "raw conversations, transcripts, API keys, tokens, redaction
  reports를 90_System/AI 또는 iCloud-synced Vault 노트에 쓰지 않습니다"

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

# UNIX 권한 비트 (8진수)
L0_DIR_MODE = 0o700
L0_FILE_MODE = 0o600

# 기본 L0 루트 — env로 override 가능 (테스트용)
L0_DEFAULT_ROOT = Path.home() / ".synapse" / "private"
L0_ENV_VAR = "SYNAPSE_L0_ROOT"


def l0_root() -> Path:
    """현재 L0 루트 경로. ``SYNAPSE_L0_ROOT`` 환경변수로 override 가능."""
    override = os.environ.get(L0_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return L0_DEFAULT_ROOT


def ensure_l0_root_secure() -> Path:
    """L0 루트 디렉토리(``~/.synapse/private``) 자체를 0700으로 보장.

    이전에 다른 도구가 0755 등 약한 권한으로 만들어놨을 수 있어 setup 시점에 강제.
    """
    return ensure_secure_dir(l0_root())


def ensure_secure_dir(path: Path) -> Path:
    """디렉토리 생성 (없으면) + 권한 0700 강제.

    이미 존재하면 권한만 갱신. 부모 디렉토리도 재귀 생성하되 부모 권한은 손대지 않음.

    Args:
        path: 대상 디렉토리. expanduser() 적용 후 사용.

    Returns:
        절대화/정규화된 Path.
    """
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(resolved, L0_DIR_MODE)
    return resolved


def ensure_secure_file(path: Path) -> Path:
    """파일 권한을 0600으로 강제. 파일이 없으면 빈 파일 생성하지 않고 그냥 반환.

    Args:
        path: 대상 파일.

    Returns:
        expanduser/resolve 적용된 Path.
    """
    resolved = path.expanduser().resolve()
    if resolved.exists() and resolved.is_file():
        with contextlib.suppress(OSError):
            os.chmod(resolved, L0_FILE_MODE)
    return resolved


def secure_write_text(path: Path, content: str) -> Path:
    """안전 모드(0600)로 텍스트 파일 작성. 부모 디렉토리는 0700으로 보장."""
    resolved = path.expanduser().resolve()
    ensure_secure_dir(resolved.parent)
    resolved.write_text(content, encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(resolved, L0_FILE_MODE)
    return resolved
