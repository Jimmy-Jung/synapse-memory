#!/usr/bin/env python3
"""
Reflect an approved MemoryInbox candidate into long-term memory.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_inbox_review as review
import synapse_memory_guard as guard


AI_ROOT = SCRIPT_DIR.parent
DEFAULT_INBOX_DIR = AI_ROOT / "MemoryInbox"
DEFAULT_PROFILE = AI_ROOT / "Profile.md"
DEFAULT_PATTERNS = AI_ROOT / "DecisionPatterns.md"
DEFAULT_REGISTRY = AI_ROOT / "DecisionQualityRegistry.md"


class ReflectError(Exception):
    """Raised when a candidate cannot be reflected safely."""


def today() -> str:
    return dt.date.today().isoformat()


def parse_decision_metadata(decision: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for part in decision.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            metadata[key] = value.strip()
    return metadata


def find_candidate(candidate_id: str, inbox_dir: Path = DEFAULT_INBOX_DIR) -> dict[str, str]:
    for path in sorted(inbox_dir.glob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("| MC-"):
                continue
            cells = review.split_markdown_row(line)
            if len(cells) < 7 or cells[0] != candidate_id:
                continue
            return {
                "candidate_id": cells[0],
                "source": cells[1],
                "candidate": cells[2].replace("<br>", "\n"),
                "confidence": cells[3],
                "risk": cells[4],
                "status": cells[5],
                "decision": cells[6],
                "inbox_path": str(path),
            }
    raise ReflectError(f"candidate not found: {candidate_id}")


def destination_for(memory_type: str) -> str:
    if memory_type == "profile":
        return "profile"
    if memory_type in {"decision_pattern", "project_context"}:
        return "patterns"
    if memory_type == "decision_quality":
        return "registry"
    raise ReflectError(f"unsupported memory_type for reflect: {memory_type}")


def ensure_section(text: str, heading: str) -> str:
    if f"\n{heading}\n" in text or text.startswith(heading + "\n"):
        return text.rstrip() + "\n"
    return text.rstrip() + f"\n\n{heading}\n\n"


def append_bullet(path: Path, heading: str, line: str) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    text = ensure_section(text, heading)
    return text + line


def registry_row(candidate: dict[str, str], metadata: dict[str, str]) -> str:
    ttl = metadata.get("ttl", "")
    return (
        f"| DQR-{dt.date.today().strftime('%Y%m%d')}-{candidate['candidate_id']} "
        f"| {candidate['candidate']} "
        f"| {candidate['source']} "
        f"| {candidate['confidence']} "
        f"| {ttl} "
        f"| active "
        f"| {today()} "
        f"| reflected from {candidate['candidate_id']} |\n"
    )


def build_reflection(candidate: dict[str, str], metadata: dict[str, str]) -> tuple[str, str]:
    if candidate["status"] != "approved":
        raise ReflectError("candidate status must be approved before reflect")
    if candidate["risk"] == "high":
        raise ReflectError("risk=high candidates cannot be reflected")
    guard.assert_no_redaction_hits(candidate["candidate"])

    memory_type = metadata.get("memory_type")
    if not memory_type:
        raise ReflectError("decision metadata missing memory_type")
    destination = destination_for(memory_type)
    source = candidate["source"]
    ttl = metadata.get("ttl", "")
    line = f"- {candidate['candidate']} (source: {source}; confidence: {candidate['confidence']}; ttl: {ttl}; id: {candidate['candidate_id']})\n"
    return destination, line


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def reflect_candidate(
    candidate_id: str,
    *,
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    profile_path: Path = DEFAULT_PROFILE,
    patterns_path: Path = DEFAULT_PATTERNS,
    registry_path: Path = DEFAULT_REGISTRY,
    apply: bool = False,
) -> dict[str, Any]:
    candidate = find_candidate(candidate_id, inbox_dir)
    metadata = parse_decision_metadata(candidate["decision"])
    destination, line = build_reflection(candidate, metadata)

    if destination == "profile":
        target = profile_path
        new_text = append_bullet(profile_path, "## Reflected Memories", line)
    elif destination == "patterns":
        target = patterns_path
        new_text = append_bullet(patterns_path, "## Reflected Memories", line)
    else:
        target = registry_path
        base = registry_path.read_text(encoding="utf-8")
        new_text = base.rstrip() + "\n" + registry_row(candidate, metadata)

    result = {
        "candidate_id": candidate_id,
        "destination": str(target),
        "apply": apply,
        "preview": line.strip() if destination != "registry" else registry_row(candidate, metadata).strip(),
    }
    if apply:
        atomic_write(target, new_text)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reflect an approved MemoryInbox candidate")
    parser.add_argument("candidate_id")
    parser.add_argument("--apply", action="store_true", help="write changes; default only previews")
    args = parser.parse_args(argv)
    try:
        result = reflect_candidate(args.candidate_id, apply=args.apply)
    except (ReflectError, guard.RedactionBlockedError, OSError) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
