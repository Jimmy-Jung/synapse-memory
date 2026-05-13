"""Installer/doctor 로그 helper.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from synapse_memory.storage.l0 import ensure_secure_dir

SENSITIVE_KEY_RE = re.compile(
    r"\b(raw_content|prompt|response|token|oauth|secret|password)=\S+",
    re.IGNORECASE,
)


def sanitize_log_message(message: str) -> str:
    """로그에 들어가면 안 되는 key=value 값을 제거한다."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return f"{key}=[redacted]"

    return SENSITIVE_KEY_RE.sub(replace, message)


class InstallerLogger:
    """한 installer/doctor 실행의 append-only 텍스트 로그."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        ensure_secure_dir(self.path.parent)

    def write_step(
        self,
        step_id: str,
        status: str,
        summary: str,
        *,
        elapsed_ms: int = 0,
    ) -> None:
        timestamp = dt.datetime.now(dt.UTC).isoformat()
        clean = sanitize_log_message(summary)
        line = f"{timestamp} {step_id} {status} {elapsed_ms}ms {clean}\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
