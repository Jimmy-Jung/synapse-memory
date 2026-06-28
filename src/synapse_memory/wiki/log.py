# src/synapse_memory/wiki/log.py
"""~/.synapse/private/log.md — ingest/lint 변경의 시간순 1줄 기록.

vault 외부(iCloud sync 제외, 0700)에 두어 Obsidian/동기화 잡음을 만들지 않으면서
grep 친화 audit trail은 유지한다. cost/feedback 로그와 같은 L0 디렉터리에 산다.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from synapse_memory.storage.l0 import ensure_l0_root_secure, l0_root

LOG_FILENAME = "log.md"
_HEADER = "# Wiki Change Log\n\n"
MAX_LOG_MESSAGE_CHARS = 240
_SAFE_ERROR_FIELDS = ("provider", "status", "category", "retry_after", "message")
_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(session[_-]?id|request[_-]?id|api[_-]?key|authorization|token)"
    r"([\"']?\s*[:=]\s*[\"']?)(?:(?:bearer|basic|token)\s+)?[^\"'\s,}]+"
)
_STATUS_RE = re.compile(r"\b(?:status|code|error code)\D{0,8}(\d{3})\b", re.IGNORECASE)


def log_path() -> Path:
    ensure_l0_root_secure()
    return l0_root() / LOG_FILENAME


def _truncate(text: str, max_chars: int = MAX_LOG_MESSAGE_CHARS) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def _parse_payload(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(candidate)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _redact_operational_ids(text: str) -> str:
    return _SENSITIVE_FIELD_RE.sub(r"\1\2<redacted>", text)


def sanitize_log_message(message: str, *, max_chars: int = MAX_LOG_MESSAGE_CHARS) -> str:
    """vault-visible 로그에 남길 수 있는 한 줄 요약으로 정리한다."""
    return _truncate(_redact_operational_ids(message), max_chars)


def summarize_provider_error(exc: Exception) -> str:
    """provider exception 원문에서 vault-visible safe summary만 추출한다."""
    raw = str(exc)
    payload = _parse_payload(raw)
    status_match = _STATUS_RE.search(raw)
    safe: dict[str, object] = {}
    if status_match:
        safe["status"] = int(status_match.group(1))

    if payload is not None:
        error = payload.get("error")
        source = error if isinstance(error, dict) else payload
        if "provider" in payload:
            safe["provider"] = payload["provider"]
        if "status" in payload and "status" not in safe:
            safe["status"] = payload["status"]
        category = source.get("type") or source.get("code") or payload.get("category")
        if category is not None:
            safe["category"] = category
        retry_after = payload.get("retry_after") or source.get("retry_after")
        if retry_after is not None:
            safe["retry_after"] = retry_after
        message = source.get("message") or payload.get("message")
        if message is not None:
            safe["message"] = sanitize_log_message(str(message), max_chars=160)

    if safe:
        ordered = {key: safe[key] for key in _SAFE_ERROR_FIELDS if key in safe}
        return _truncate(json.dumps(ordered, ensure_ascii=False, sort_keys=True))
    return _truncate(f"{type(exc).__name__}: {_redact_operational_ids(raw)}")


def append_log(message: str, *, when: str | None = None) -> Path:
    """log.md에 '- <iso> <message>' 한 줄 추가. 파일/헤더 없으면 생성."""
    path = log_path()
    stamp = when or datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"- {stamp} {sanitize_log_message(message)}\n"
    if not path.is_file():
        path.write_text(_HEADER + line, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return path
