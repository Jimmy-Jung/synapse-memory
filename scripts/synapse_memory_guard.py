#!/usr/bin/env python3
"""
Synapse AI Memory guard.

Author: JunyoungJung
Date: 2026-04-23

Validates SessionRecord-v1 data and applies fail-closed redaction checks before
anything is allowed to be written into _System/AI.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_SOURCES = {"claude", "codex", "cursor", "manual"}
ALLOWED_REDACTION_STATUSES = {"pending", "passed", "blocked", "failed"}
ALLOWED_ROLES = {"user", "assistant", "tool", "system", "unknown"}


@dataclasses.dataclass(frozen=True)
class RedactionHit:
    pattern_name: str
    line_number: int
    excerpt: str


class ValidationError(Exception):
    """Raised when a SessionRecord-v1 object is invalid."""


class RedactionBlockedError(Exception):
    """Raised when redaction detects sensitive or unsafe content."""


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "shell_export_secret",
        re.compile(
            r"\bexport\s+[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY)"
            r"\s*=\s*[\"']?[^\"'\s]+",
            re.IGNORECASE,
        ),
    ),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+|DSA\s+)?PRIVATE\s+KEY-----",
            re.IGNORECASE,
        ),
    ),
    (
        "password_assignment",
        re.compile(r"\b(?:password|passwd|pwd)\s*[:=]\s*[\"']?[^\"'\s]{6,}", re.IGNORECASE),
    ),
    (
        "database_url_with_credentials",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^:\s/]+:[^@\s/]+@[^ \n]+", re.IGNORECASE),
    ),
    (
        "service_account_private_key",
        re.compile(r"\"private_key\"\s*:\s*\"-----BEGIN\s+PRIVATE\s+KEY-----", re.IGNORECASE),
    ),
    (
        "prompt_injection_instruction",
        re.compile(
            r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior)\s+instructions\b",
            re.IGNORECASE,
        ),
    ),
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_iso_datetime(value: Any, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be an ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    try:
        dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be ISO-8601: {value}") from exc


def find_redaction_hits(text: str) -> list[RedactionHit]:
    hits: list[RedactionHit] = []
    lines = text.splitlines() or [text]
    for line_number, line in enumerate(lines, start=1):
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                hits.append(
                    RedactionHit(
                        pattern_name=name,
                        line_number=line_number,
                        excerpt=line[:120],
                    )
                )
    return hits


def assert_no_redaction_hits(text: str) -> None:
    hits = find_redaction_hits(text)
    if hits:
        names = ", ".join(f"{hit.pattern_name}@{hit.line_number}" for hit in hits)
        raise RedactionBlockedError(f"redaction blocked content: {names}")


def require_string(record: dict[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} is required")
    return value


def validate_message(message: Any, index: int) -> None:
    if not isinstance(message, dict):
        raise ValidationError(f"messages[{index}] must be an object")

    role = require_string(message, "role")
    if role not in ALLOWED_ROLES:
        raise ValidationError(f"messages[{index}].role is invalid: {role}")

    content = require_string(message, "content")
    assert_no_redaction_hits(content)

    content_hash = require_string(message, "content_hash")
    expected_hash = sha256_text(content)
    if content_hash != expected_hash:
        raise ValidationError(
            f"messages[{index}].content_hash mismatch: expected {expected_hash}"
        )

    parse_iso_datetime(message.get("created_at"), f"messages[{index}].created_at")

    metadata = message.get("metadata", {})
    if metadata is not None and not isinstance(metadata, dict):
        raise ValidationError(f"messages[{index}].metadata must be an object")


def validate_session_record(record: dict[str, Any]) -> None:
    schema_version = require_string(record, "schema_version")
    if schema_version != "SessionRecord-v1":
        raise ValidationError(f"schema_version must be SessionRecord-v1: {schema_version}")

    source = require_string(record, "source")
    if source not in ALLOWED_SOURCES:
        raise ValidationError(f"source is invalid: {source}")

    require_string(record, "source_session_id")
    parse_iso_datetime(require_string(record, "collected_at"), "collected_at")
    require_string(record, "source_path")
    require_string(record, "content_hash")

    redaction_status = require_string(record, "redaction_status")
    if redaction_status not in ALLOWED_REDACTION_STATUSES:
        raise ValidationError(f"redaction_status is invalid: {redaction_status}")
    if redaction_status != "passed":
        raise RedactionBlockedError(
            f"redaction_status must be passed before Vault write: {redaction_status}"
        )

    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValidationError("messages must be an array")
    if not messages:
        raise ValidationError("messages must not be empty")

    for index, message in enumerate(messages):
        validate_message(message, index)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValidationError("top-level JSON must be an object")
    return value


def command_scan_text(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = find_redaction_hits(text)
    if hits:
        for hit in hits:
            print(
                f"BLOCKED {hit.pattern_name} line={hit.line_number} excerpt={hit.excerpt}",
                file=sys.stderr,
            )
        return 2
    print("PASSED")
    return 0


def command_validate_session(path: Path) -> int:
    record = load_json(path)
    validate_session_record(record)
    print("PASSED")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synapse AI Memory guard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_text = subparsers.add_parser("scan-text", help="scan a text file for blocked content")
    scan_text.add_argument("path", type=Path)

    validate_session = subparsers.add_parser(
        "validate-session", help="validate a SessionRecord-v1 JSON file"
    )
    validate_session.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "scan-text":
            return command_scan_text(args.path)
        if args.command == "validate-session":
            return command_validate_session(args.path)
    except (ValidationError, RedactionBlockedError) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
