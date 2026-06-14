# src/synapse_memory/wiki/log.py
"""vault 루트 log.md — ingest/lint 변경의 시간순 1줄 기록 (grep 친화).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path

LOG_FILENAME = "log.md"
_HEADER = "# Wiki Change Log\n\n"


def log_path(*, vault_path: Path | None = None) -> Path:
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / LOG_FILENAME


def append_log(message: str, *, vault_path: Path | None = None, when: str | None = None) -> Path:
    """log.md에 '- <iso> <message>' 한 줄 추가. 파일/헤더 없으면 생성."""
    path = log_path(vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = when or datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"- {stamp} {message}\n"
    if not path.is_file():
        path.write_text(_HEADER + line, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return path
