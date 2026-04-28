#!/usr/bin/env python3
"""
Codex source adapter for Synapse AI Memory.

Author: jimmy
Date: 2026-04-28

Codex CLI 세션(`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`)을 SessionRecord-v1
JSON으로 변환한다. 두 단계 소스:

1. **Primary**: `~/.codex/session_index.jsonl` 의 `{id, thread_name, updated_at}` 라인을
   기준으로 신규/업데이트된 세션 ID를 식별 → 해당 rollout 파일 경로 매핑
2. **Fallback**: index 파일이 없거나 손상되면 sessions/ 디렉토리를 직접 스캔

raw 데이터는 절대 vault로 흘러가지 않는다. 정규화 결과는 ~/.synapse/private/normalized/codex/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import synapse_memory_guard as guard
import synapse_checkpoint as checkpoint


PRIVATE_ROOT = Path.home() / ".synapse" / "private"
DEFAULT_OUT_DIR = PRIVATE_ROOT / "normalized" / "codex"
DEFAULT_REPORT_DIR = PRIVATE_ROOT / "redaction-reports"
DEFAULT_CODEX_ROOT = Path.home() / ".codex"
DEFAULT_INDEX = DEFAULT_CODEX_ROOT / "session_index.jsonl"
DEFAULT_SESSIONS_DIR = DEFAULT_CODEX_ROOT / "sessions"
DEFAULT_RECENT_DAYS = 7


class CodexInputError(Exception):
    """Raised when neither index nor sessions directory yields usable input."""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


# ---------- discovery ----------


def _read_index_ids(index_path: Path) -> list[dict[str, Any]]:
    """session_index.jsonl 라인을 dict 리스트로. 손상된 라인은 skip."""
    if not index_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            entries.append(item)
    return entries


def _scan_sessions_dir(
    sessions_dir: Path,
    *,
    since_dt: dt.datetime | None = None,
) -> list[Path]:
    """sessions/ 직접 스캔 (fallback). since_dt 이후 mtime만."""
    if not sessions_dir.is_dir():
        return []
    files: list[Path] = []
    for p in sessions_dir.rglob("rollout-*.jsonl"):
        if not p.is_file():
            continue
        if since_dt is not None:
            mtime = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.UTC)
            if mtime < since_dt:
                continue
        files.append(p)
    files.sort(key=lambda x: x.stat().st_mtime)
    return files


def _resolve_rollout_for_id(session_id: str, sessions_dir: Path) -> Path | None:
    """session_id가 파일명에 포함된 rollout-*.jsonl 검색."""
    if not sessions_dir.is_dir():
        return None
    for p in sessions_dir.rglob(f"rollout-*-{session_id}.jsonl"):
        if p.is_file():
            return p
    return None


def discover_sessions(
    *,
    index_path: Path = DEFAULT_INDEX,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
    since_dt: dt.datetime | None = None,
    backfill: bool = False,
) -> list[Path]:
    """수집 대상 rollout-*.jsonl 경로 목록.

    Strategy:
      - index 시도 → id로 rollout 매핑
      - index 비어있거나 매핑 실패 → fallback 디렉토리 스캔 사용
    backfill=True면 since_dt 무시.
    """
    cutoff = None if backfill else since_dt
    primary: list[Path] = []
    seen_paths: set[Path] = set()

    for entry in _read_index_ids(index_path):
        rollout = _resolve_rollout_for_id(entry["id"], sessions_dir)
        if rollout is None:
            continue
        if cutoff is not None:
            mtime = dt.datetime.fromtimestamp(rollout.stat().st_mtime, tz=dt.UTC)
            if mtime < cutoff:
                continue
        if rollout in seen_paths:
            continue
        primary.append(rollout)
        seen_paths.add(rollout)

    if primary:
        return primary

    # Fallback: index 손상/누락
    return [p for p in _scan_sessions_dir(sessions_dir, since_dt=cutoff) if p not in seen_paths]


# ---------- parsing ----------


def _payload_text(payload: Any) -> str:
    """payload에서 사용자에게 의미있는 텍스트만 추출. 없으면 빈 문자열."""
    if isinstance(payload, dict):
        for key in ("message", "text", "content", "value", "summary"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        # nested message
        msg = payload.get("message")
        if isinstance(msg, dict):
            inner = msg.get("content")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
            if isinstance(inner, list):
                parts = [
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in inner
                ]
                joined = "\n".join(p for p in parts if p)
                if joined.strip():
                    return joined.strip()
    if isinstance(payload, str):
        return payload.strip()
    return ""


def _classify_role(line_type: str, payload: Any) -> str:
    if isinstance(payload, dict):
        role = payload.get("role")
        if isinstance(role, str) and role in guard.ALLOWED_ROLES:
            return role
        if role == "human":
            return "user"
    if line_type in {"user_msg", "user_message"}:
        return "user"
    if line_type in {"assistant_msg", "assistant_message", "agent_msg"}:
        return "assistant"
    if line_type in {"tool_call", "tool_result", "function_call"}:
        return "tool"
    if line_type in {"session_meta", "system"}:
        return "system"
    return "unknown"


def parse_rollout(path: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """rollout JSONL을 (session_id, messages, meta) 튜플로.

    meta에는 session_meta payload (cwd, model_provider, cli_version 등) 보존.
    """
    session_id = path.stem.split("-", 5)[-1]  # rollout-YYYY-MM-DDThh-mm-ss-<uuid> → uuid 부분
    messages: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}

    for line_number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        line_type = str(item.get("type") or "")
        payload = item.get("payload")
        timestamp = item.get("timestamp") if isinstance(item.get("timestamp"), str) else None

        if line_type == "session_meta" and isinstance(payload, dict):
            if isinstance(payload.get("id"), str):
                session_id = payload["id"]
            meta = {
                k: payload.get(k)
                for k in ("cwd", "originator", "cli_version", "source", "model_provider")
                if k in payload
            }
            continue

        text = _payload_text(payload)
        if not text:
            continue

        messages.append(
            {
                "role": _classify_role(line_type, payload),
                "created_at": timestamp,
                "content": text,
                "content_hash": guard.sha256_text(text),
                "metadata": {"line_number": line_number, "type": line_type},
            }
        )

    return session_id, messages, meta


# ---------- collection ----------


def _write_redaction_report(report_dir: Path, source_path: Path, hits: list[guard.RedactionHit]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"codex-{guard.sha256_text(str(source_path))[:16]}-redaction.json"
    payload = {
        "source": "codex",
        "source_path": str(source_path),
        "created_at": utc_now(),
        "status": "blocked",
        "hits": [
            {"pattern_name": h.pattern_name, "line_number": h.line_number, "excerpt": h.excerpt}
            for h in hits
        ],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def _sanitize_filename(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "-", value)[:180]


def collect_file(
    path: Path,
    out_dir: Path = DEFAULT_OUT_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    dry_run: bool = False,
    use_checkpoint: bool = False,
    checkpoint_base_dir: Path | None = None,
) -> Path | None:
    source_path = path.expanduser().resolve()
    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    content_hash = guard.sha256_text(raw_text)

    if use_checkpoint and checkpoint.has_seen("codex", content_hash, base_dir=checkpoint_base_dir):
        return None

    raw_hits = guard.find_redaction_hits(raw_text)
    if raw_hits:
        if not dry_run:
            report_path = _write_redaction_report(report_dir, source_path, raw_hits)
            raise guard.RedactionBlockedError(f"source blocked; report={report_path}")
        raise guard.RedactionBlockedError(f"source blocked (dry-run); hits={len(raw_hits)}")

    session_id, messages, meta = parse_rollout(source_path)
    if not messages:
        # 메시지가 없으면 schema validation에서 실패. drop으로 처리.
        raise CodexInputError(f"no parseable messages: {source_path}")

    record = {
        "schema_version": "SessionRecord-v1",
        "source": "codex",
        "source_session_id": session_id,
        "collected_at": utc_now(),
        "source_path": str(source_path),
        "content_hash": content_hash,
        "redaction_status": "passed",
        "messages": messages,
        "metadata": meta,
    }
    guard.validate_session_record(record)

    if dry_run:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"codex-{session_id}-{content_hash[:12]}.json"
    output_path = out_dir / _sanitize_filename(output_name)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    if use_checkpoint:
        checkpoint.save(
            "codex",
            last_processed_path=str(source_path),
            add_content_hash=content_hash,
            base_dir=checkpoint_base_dir,
        )
    return output_path


def collect_recent(
    *,
    index_path: Path = DEFAULT_INDEX,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    days: int = DEFAULT_RECENT_DAYS,
    backfill: bool = False,
    dry_run: bool = False,
    use_checkpoint: bool = True,
    checkpoint_base_dir: Path | None = None,
) -> dict[str, Any]:
    """최근 N일치 Codex 세션을 일괄 수집."""
    if backfill:
        cutoff = None
    else:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)

    targets = discover_sessions(
        index_path=index_path,
        sessions_dir=sessions_dir,
        since_dt=cutoff,
        backfill=backfill,
    )

    processed: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []

    for target in targets:
        try:
            output = collect_file(
                target,
                out_dir,
                report_dir,
                dry_run=dry_run,
                use_checkpoint=use_checkpoint,
                checkpoint_base_dir=checkpoint_base_dir,
            )
        except (
            guard.ValidationError,
            guard.RedactionBlockedError,
            CodexInputError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            errors.append({"path": str(target), "reason": f"{type(exc).__name__}: {exc}"})
            continue

        if output is None:
            skipped.append(str(target))
        else:
            processed.append(str(output))

    return {"processed": processed, "skipped": skipped, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Codex sessions into SessionRecord-v1")
    parser.add_argument("--path", type=Path, help="단일 rollout 파일 처리")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--days", type=int, default=DEFAULT_RECENT_DAYS)
    parser.add_argument("--backfill", action="store_true", help="전체 history 처리 (기본 OFF)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-checkpoint", action="store_true", help="checkpoint dedup 비활성화")
    args = parser.parse_args(argv)

    use_checkpoint = not args.no_checkpoint

    try:
        if args.path is not None:
            output = collect_file(
                args.path,
                args.out_dir,
                args.report_dir,
                dry_run=args.dry_run,
                use_checkpoint=use_checkpoint,
            )
            if output is None:
                print("(dry-run or checkpoint dedup; no output written)")
                return 0
            print(output)
            return 0

        result = collect_recent(
            index_path=args.index,
            sessions_dir=args.sessions_dir,
            out_dir=args.out_dir,
            report_dir=args.report_dir,
            days=args.days,
            backfill=args.backfill,
            dry_run=args.dry_run,
            use_checkpoint=use_checkpoint,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0

    except (
        guard.ValidationError,
        guard.RedactionBlockedError,
        CodexInputError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
