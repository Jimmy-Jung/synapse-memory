"""API key 등 credential 파일 관리.

위치: ``~/.synapse/private/credentials/<service>.json`` (0600).

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any, cast

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

CREDENTIALS_SUBDIR = "credentials"


def credentials_dir() -> Path:
    return l0_root() / CREDENTIALS_SUBDIR


def _credential_path(service_file: str) -> Path:
    return credentials_dir() / service_file


def save_credential(service_file: str, payload: dict[str, Any]) -> Path:
    """JSON credential 저장 (0600 강제). L0 루트도 함께 보호."""
    ensure_l0_root_secure()
    cdir = credentials_dir()
    ensure_secure_dir(cdir)

    path = _credential_path(service_file)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, L0_FILE_MODE)
    return path


def load_credential(service_file: str) -> dict[str, Any] | None:
    """없거나 파싱 실패면 None."""
    path = _credential_path(service_file)
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else None
    except (json.JSONDecodeError, OSError):
        return None
