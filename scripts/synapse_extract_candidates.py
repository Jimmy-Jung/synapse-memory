#!/usr/bin/env python3
"""
Heuristic MemoryCandidate extractor for Synapse AI Memory.

Author: JunyoungJung
Date: 2026-04-28

Reads one SessionRecord-v1 JSON file and emits pending MemoryCandidate-v1
objects. No LLM calls. Candidate text is guard-scanned before output.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_memory_guard as guard


MIN_COLLECTED_AT_UTC = dt.datetime(2026, 4, 28, tzinfo=dt.UTC)

EXPLICIT_MEMORY_PATTERNS = (
    "기억해줘",
    "기억해 줘",
    "앞으로는",
    "다음부터는",
    "잊지마",
    "remember this",
    "from now on",
)
PLAN_MARKERS = ("/plan", "/autoplan", "ExitPlanMode")
APPROVAL_PATTERNS = (
    "approve",
    "approved",
    "yes",
    "ok",
    "okay",
    "go ahead",
    "진행",
    "승인",
    "좋아",
)
PROJECT_NOUNS = ("메모어", "메가스터디", "Synapse", "AI Memory")
PROJECT_STATUS_PATTERNS = (
    "참여 중",
    "진행 중",
    "작업 중",
    "운영 중",
    "준비 중",
    "시작",
    "마감",
    "목표",
)
DATE_PATTERN = re.compile(
    r"(?:20\d{2}[-./년]\s*\d{1,2}(?:[-./월]\s*\d{1,2})?|"
    r"\d{1,2}[-./월]\s*\d{1,2}|"
    r"\d{1,2}\s*주차)"
)


class CandidateExtractionError(Exception):
    """Raised when input is unsafe or structurally invalid."""


def parse_iso_datetime(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise CandidateExtractionError("collected_at is required")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateExtractionError(f"invalid collected_at: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def first_line(value: str, *, limit: int = 240) -> str:
    text = normalize_space(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def candidate_ttl(memory_type: str, collected_at: dt.datetime) -> str:
    days_by_type = {
        "profile": 180,
        "decision_pattern": 90,
        "decision_quality": 90,
        "project_context": 90,
    }
    days = days_by_type.get(memory_type, 90)
    return (collected_at.date() + dt.timedelta(days=days)).isoformat()


def is_guard_blocked(text: str) -> bool:
    return bool(guard.find_redaction_hits(text))


def safe_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("risk") == "high":
        return False
    return not (
        is_guard_blocked(str(candidate.get("candidate", "")))
        or is_guard_blocked(str(candidate.get("evidence", "")))
    )


def validate_record_for_extraction(record: dict[str, Any]) -> None:
    if record.get("schema_version") != "SessionRecord-v1":
        raise CandidateExtractionError("schema_version must be SessionRecord-v1")
    source = record.get("source")
    if source not in guard.ALLOWED_SOURCES:
        raise CandidateExtractionError(f"invalid source: {source}")
    if not isinstance(record.get("source_session_id"), str) or not record["source_session_id"]:
        raise CandidateExtractionError("source_session_id is required")
    if record.get("redaction_status") != "passed":
        raise guard.RedactionBlockedError(
            f"redaction_status must be passed: {record.get('redaction_status')}"
        )
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise CandidateExtractionError("messages must be an array")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise CandidateExtractionError(f"messages[{index}] must be an object")
        content = message.get("content")
        if not isinstance(content, str):
            raise CandidateExtractionError(f"messages[{index}].content must be a string")
        content_hash = message.get("content_hash")
        if content_hash != guard.sha256_text(content):
            raise CandidateExtractionError(f"messages[{index}].content_hash mismatch")


def classify_explicit_memory(text: str) -> str:
    lowered = text.lower()
    work_markers = (
        "계획",
        "작업",
        "진행",
        "검증",
        "테스트",
        "리뷰",
        "코드",
        "구현",
        "먼저",
        "확인",
        "plan",
        "test",
        "review",
        "implement",
    )
    preference_markers = ("선호", "좋아", "싫어", "말투", "답변", "스타일", "prefer", "like")
    if any(marker in lowered for marker in preference_markers):
        return "profile"
    if any(marker in lowered for marker in work_markers):
        return "decision_pattern"
    return "profile"


def add_candidate(
    bucket: list[dict[str, Any]],
    *,
    source: str,
    source_session_id: str,
    memory_type: str,
    candidate: str,
    evidence: str,
    confidence: float,
    risk: str,
    collected_at: dt.datetime,
) -> None:
    text = first_line(candidate, limit=800)
    if not text:
        return
    item = {
        "schema_version": "MemoryCandidate-v1",
        "candidate_id": "",
        "source": source,
        "source_session_id": source_session_id,
        "memory_type": memory_type,
        "candidate": text,
        "evidence": first_line(evidence, limit=240),
        "confidence": confidence,
        "risk": risk,
        "ttl": candidate_ttl(memory_type, collected_at),
        "status": "pending",
    }
    if safe_candidate(item):
        bucket.append(item)


def extract_explicit_memory(
    candidates: list[dict[str, Any]],
    record: dict[str, Any],
    collected_at: dt.datetime,
) -> None:
    for index, message in enumerate(record.get("messages", [])):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        lowered = content.lower()
        if not any(pattern.lower() in lowered for pattern in EXPLICIT_MEMORY_PATTERNS):
            continue
        add_candidate(
            candidates,
            source=record["source"],
            source_session_id=record["source_session_id"],
            memory_type=classify_explicit_memory(content),
            candidate=content,
            evidence=f"heuristic=explicit_memory_request message_index={index}",
            confidence=0.9,
            risk="low",
            collected_at=collected_at,
        )


def extract_approved_decision(
    candidates: list[dict[str, Any]],
    record: dict[str, Any],
    collected_at: dt.datetime,
) -> None:
    messages = record.get("messages", [])
    for index, message in enumerate(messages):
        content = str(message.get("content", ""))
        if not any(marker in content for marker in PLAN_MARKERS):
            continue
        for later_index in range(index + 1, len(messages)):
            later = messages[later_index]
            if later.get("role") != "user":
                continue
            reply = str(later.get("content", "")).lower()
            if any(pattern in reply for pattern in APPROVAL_PATTERNS):
                summary = first_line(content, limit=200)
                add_candidate(
                    candidates,
                    source=record["source"],
                    source_session_id=record["source_session_id"],
                    memory_type="decision_quality",
                    candidate=f"승인된 계획: {summary}",
                    evidence=(
                        "heuristic=approved_decision "
                        f"plan_message_index={index} approval_message_index={later_index}"
                    ),
                    confidence=0.8,
                    risk="medium",
                    collected_at=collected_at,
                )
                break


def extract_repeated_preference(
    candidates: list[dict[str, Any]],
    record: dict[str, Any],
    collected_at: dt.datetime,
) -> None:
    occurrences: dict[str, list[str]] = defaultdict(list)
    for message in record.get("messages", []):
        if message.get("role") != "user":
            continue
        for raw_line in str(message.get("content", "")).splitlines():
            line = first_line(raw_line, limit=240)
            if len(line) < 8:
                continue
            normalized = line.lower()
            occurrences[normalized].append(line)

    for normalized, lines in sorted(occurrences.items()):
        if len(lines) < 3:
            continue
        add_candidate(
            candidates,
            source=record["source"],
            source_session_id=record["source_session_id"],
            memory_type="profile",
            candidate=lines[0],
            evidence=f"heuristic=repeated_preference normalized={normalized[:80]} count={len(lines)}",
            confidence=0.6,
            risk="low",
            collected_at=collected_at,
        )


def extract_project_context(
    candidates: list[dict[str, Any]],
    record: dict[str, Any],
    collected_at: dt.datetime,
) -> None:
    for index, message in enumerate(record.get("messages", [])):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        if not DATE_PATTERN.search(content):
            continue
        if not any(noun in content for noun in PROJECT_NOUNS):
            continue
        if not any(status in content for status in PROJECT_STATUS_PATTERNS):
            continue
        add_candidate(
            candidates,
            source=record["source"],
            source_session_id=record["source_session_id"],
            memory_type="project_context",
            candidate=content,
            evidence=f"heuristic=project_context message_index={index}",
            confidence=0.7,
            risk="low",
            collected_at=collected_at,
        )


def candidate_id_suffix(candidate: dict[str, Any]) -> int:
    basis = json.dumps(
        {
            "source": candidate.get("source"),
            "source_session_id": candidate.get("source_session_id"),
            "memory_type": candidate.get("memory_type"),
            "candidate": candidate.get("candidate"),
            "evidence": candidate.get("evidence"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return (int(guard.sha256_text(basis)[:8], 16) % 999) + 1


def assign_candidate_ids(candidates: list[dict[str, Any]], collected_at: dt.datetime) -> None:
    date_token = collected_at.date().strftime("%Y%m%d")
    used_suffixes: set[int] = set()
    for candidate in candidates:
        suffix = candidate_id_suffix(candidate)
        for _ in range(999):
            if suffix not in used_suffixes:
                break
            suffix = (suffix % 999) + 1
        else:
            raise CandidateExtractionError("too many automated candidates for one date")
        used_suffixes.add(suffix)
        candidate["candidate_id"] = f"MC-{date_token}-A-{suffix:03d}"


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (str(candidate.get("memory_type")), str(candidate.get("candidate")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def extract_candidates_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    validate_record_for_extraction(record)
    collected_at = parse_iso_datetime(record.get("collected_at"))
    if collected_at.astimezone(dt.UTC) < MIN_COLLECTED_AT_UTC:
        return []
    if not record.get("messages"):
        return []

    candidates: list[dict[str, Any]] = []
    extract_explicit_memory(candidates, record, collected_at)
    extract_approved_decision(candidates, record, collected_at)
    extract_repeated_preference(candidates, record, collected_at)
    extract_project_context(candidates, record, collected_at)

    deduped = dedupe_candidates(candidates)
    assign_candidate_ids(deduped, collected_at)
    return deduped


def extract_candidates(path: Path) -> list[dict[str, Any]]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise CandidateExtractionError("top-level JSON must be an object")
    return extract_candidates_from_record(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract MemoryCandidate-v1 objects")
    parser.add_argument("session_record", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="parse and emit only; no writes are performed")
    args = parser.parse_args(argv)

    try:
        candidates = extract_candidates(args.session_record)
    except (CandidateExtractionError, guard.RedactionBlockedError, OSError, json.JSONDecodeError) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2

    print(json.dumps(candidates, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
