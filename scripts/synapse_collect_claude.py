#!/usr/bin/env python3
"""
Claude source adapter for Synapse AI Memory.

Author: JunyoungJung
Date: 2026-04-23
Updated: 2026-04-28 — directory mode, checkpoint-based dedup, dry-run, path-prefix guard.

Converts one or more Claude local files into redacted SessionRecord-v1 JSON files
under ~/.synapse/private/normalized. Never writes raw data into _System/AI.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_memory_guard as guard
import synapse_checkpoint as checkpoint


PRIVATE_ROOT = Path.home() / ".synapse" / "private"
DEFAULT_OUT_DIR = PRIVATE_ROOT / "normalized" / "claude"
DEFAULT_REPORT_DIR = PRIVATE_ROOT / "redaction-reports"
DEFAULT_CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


class InputPathRejected(Exception):
    """Raised when an input path fails the prefix guard (R8 hardening)."""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def coerce_content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("value")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        text = value.get("text") or value.get("content") or value.get("value")
        if isinstance(text, str):
            return text
    return str(value)


def normalize_role(value: Any) -> str:
    if isinstance(value, str) and value in guard.ALLOWED_ROLES:
        return value
    if value == "human":
        return "user"
    return "unknown"


def make_message(role: str, content: str, created_at: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": normalize_role(role),
        "created_at": created_at,
        "content": content,
        "content_hash": guard.sha256_text(content),
        "metadata": metadata,
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def resolve_source_path(path: Path) -> Path:
    if path.suffix == ".json":
        try:
            data = load_json(path)
        except Exception:
            return path
        if isinstance(data, dict) and isinstance(data.get("transcriptPath"), str):
            transcript_path = Path(data["transcriptPath"]).expanduser()
            if transcript_path.exists():
                return transcript_path
    return path


def parse_jsonl_transcript(path: Path) -> tuple[str, list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = []
    session_id = path.stem
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("sessionId"), str):
                session_id = item["sessionId"]
            message = item.get("message")
            if not isinstance(message, dict):
                continue
            content = coerce_content_to_text(message.get("content")).strip()
            if not content:
                continue
            messages.append(
                make_message(
                    role=coerce_content_to_text(message.get("role")),
                    content=content,
                    created_at=item.get("timestamp") if isinstance(item.get("timestamp"), str) else None,
                    metadata={
                        "line_number": line_number,
                        "uuid": item.get("uuid"),
                        "type": item.get("type"),
                    },
                )
            )
    return session_id, messages


def parse_markdown_plan(path: Path) -> tuple[str, list[dict[str, Any]]]:
    content = path.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        return path.stem, []
    return path.stem, [
        make_message(
            role="unknown",
            content=content,
            created_at=None,
            metadata={"format": "markdown-plan"},
        )
    ]


def parse_json_task(path: Path) -> tuple[str, list[dict[str, Any]]]:
    data = load_json(path)
    if not isinstance(data, dict):
        return path.stem, []
    session_id = str(data.get("id") or path.stem)
    parts: list[str] = []
    for key in ("subject", "description", "activeForm", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}: {value.strip()}")
    if not parts:
        return session_id, []
    return session_id, [
        make_message(
            role="unknown",
            content="\n".join(parts),
            created_at=None,
            metadata={"format": "claude-task-json"},
        )
    ]


def parse_source(path: Path) -> tuple[str, list[dict[str, Any]]]:
    resolved = resolve_source_path(path)
    if resolved.suffix == ".jsonl":
        return parse_jsonl_transcript(resolved)
    if resolved.suffix == ".md":
        return parse_markdown_plan(resolved)
    if resolved.suffix == ".json":
        return parse_json_task(resolved)
    content = resolved.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        return resolved.stem, []
    return resolved.stem, [
        make_message("unknown", content, None, {"format": resolved.suffix.lstrip(".") or "text"})
    ]


def write_redaction_report(report_dir: Path, source_path: Path, hits: list[guard.RedactionHit]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"claude-{guard.sha256_text(str(source_path))[:16]}-redaction.json"
    payload = {
        "source": "claude",
        "source_path": str(source_path),
        "created_at": utc_now(),
        "status": "blocked",
        "hits": [dataclasses_to_dict(hit) for hit in hits],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def dataclasses_to_dict(hit: guard.RedactionHit) -> dict[str, Any]:
    return {
        "pattern_name": hit.pattern_name,
        "line_number": hit.line_number,
        "excerpt": hit.excerpt,
    }


def verify_input_path(path: Path, *, require_prefix: Path | None = None) -> Path:
    """입력 경로가 허용된 prefix 안에 있는지 검증 (R8 hook self-loop 방지).

    require_prefix가 None이면 검증 skip (backward compat).
    """
    resolved = path.expanduser().resolve()
    if require_prefix is None:
        return resolved
    prefix = require_prefix.expanduser().resolve()
    try:
        resolved.relative_to(prefix)
    except ValueError as exc:
        raise InputPathRejected(
            f"input path {resolved} is not under required prefix {prefix}"
        ) from exc
    return resolved


def collect_file(
    path: Path,
    out_dir: Path = DEFAULT_OUT_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    require_prefix: Path | None = None,
    dry_run: bool = False,
    checkpoint_base_dir: Path | None = None,
    use_checkpoint: bool = False,
) -> Path | None:
    """단일 파일을 SessionRecord-v1 JSON으로 변환.

    Parameters
    ----------
    require_prefix : R8 가드 — path가 이 prefix 안에 있어야 처리 (CLI에서 hook 시 활성화)
    dry_run : True면 redaction 검증·파싱·schema 검증까지 하되 파일 쓰기 X. 결과 path 대신 None 반환
    use_checkpoint : True면 동일 content_hash 처리 시 None 반환 (멱등성)
    """
    source_path = verify_input_path(path, require_prefix=require_prefix)
    resolved_path = resolve_source_path(source_path)
    raw_text = resolved_path.read_text(encoding="utf-8", errors="replace")
    content_hash = guard.sha256_text(raw_text)

    if use_checkpoint and checkpoint.has_seen("claude", content_hash, base_dir=checkpoint_base_dir):
        return None

    raw_hits = guard.find_redaction_hits(raw_text)
    if raw_hits:
        if not dry_run:
            report_path = write_redaction_report(report_dir, resolved_path, raw_hits)
            raise guard.RedactionBlockedError(f"source blocked; report={report_path}")
        raise guard.RedactionBlockedError(f"source blocked (dry-run); hits={len(raw_hits)}")

    source_session_id, messages = parse_source(source_path)
    record = {
        "schema_version": "SessionRecord-v1",
        "source": "claude",
        "source_session_id": source_session_id,
        "collected_at": utc_now(),
        "source_path": str(resolved_path),
        "content_hash": content_hash,
        "redaction_status": "passed",
        "messages": messages,
    }
    guard.validate_session_record(record)

    if dry_run:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"claude-{source_session_id}-{record['content_hash'][:12]}.json"
    output_path = out_dir / sanitize_filename(output_name)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    if use_checkpoint:
        checkpoint.save(
            "claude",
            last_processed_path=str(resolved_path),
            add_content_hash=content_hash,
            base_dir=checkpoint_base_dir,
        )

    return output_path


def collect_directory(
    directory: Path,
    out_dir: Path = DEFAULT_OUT_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    require_prefix: Path | None = None,
    dry_run: bool = False,
    checkpoint_base_dir: Path | None = None,
    use_checkpoint: bool = True,
    pattern: str = "*.jsonl",
) -> dict[str, Any]:
    """디렉토리 안의 .jsonl 파일을 일괄 수집. checkpoint dedup 기본 ON.

    Returns
    -------
    {"processed": [paths], "skipped": [paths], "errors": [{path, reason}]}
    """
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"{directory} is not a directory")

    processed: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []

    for source in sorted(directory.glob(pattern)):
        try:
            output = collect_file(
                source,
                out_dir,
                report_dir,
                require_prefix=require_prefix,
                dry_run=dry_run,
                checkpoint_base_dir=checkpoint_base_dir,
                use_checkpoint=use_checkpoint,
            )
        except (
            guard.ValidationError,
            guard.RedactionBlockedError,
            InputPathRejected,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            errors.append({"path": str(source), "reason": f"{type(exc).__name__}: {exc}"})
            continue

        if output is None:
            skipped.append(str(source))
        else:
            processed.append(str(output))

    return {"processed": processed, "skipped": skipped, "errors": errors}


def sanitize_filename(value: str) -> str:
    return re_sub(r"[^A-Za-z0-9._-]+", "-", value)[:180]


def re_sub(pattern: str, replacement: str, value: str) -> str:
    import re

    return re.sub(pattern, replacement, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Claude file(s) into SessionRecord-v1")
    parser.add_argument("path", type=Path, help="파일 또는 (--directory와 함께) 디렉토리")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--directory", action="store_true", help="path를 디렉토리로 취급, 안의 .jsonl 일괄 수집")
    parser.add_argument(
        "--require-prefix",
        type=Path,
        default=None,
        help=f"입력 path가 이 prefix 안에 있어야 처리 (R8 가드). 권장: {DEFAULT_CLAUDE_PROJECTS_ROOT}",
    )
    parser.add_argument("--dry-run", action="store_true", help="검증·파싱만, 출력 파일 작성 X")
    parser.add_argument(
        "--use-checkpoint",
        action="store_true",
        help="checkpoint 기반 dedup 활성화 (단일 파일 모드에서도 사용 가능)",
    )
    args = parser.parse_args(argv)

    try:
        if args.directory:
            result = collect_directory(
                args.path,
                args.out_dir,
                args.report_dir,
                require_prefix=args.require_prefix,
                dry_run=args.dry_run,
                use_checkpoint=True,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result["errors"] else 0

        output = collect_file(
            args.path,
            args.out_dir,
            args.report_dir,
            require_prefix=args.require_prefix,
            dry_run=args.dry_run,
            use_checkpoint=args.use_checkpoint,
        )
    except (
        guard.ValidationError,
        guard.RedactionBlockedError,
        InputPathRejected,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2

    if output is None:
        print("(dry-run or checkpoint dedup; no output written)")
        return 0
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
