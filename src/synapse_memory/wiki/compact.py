"""Raw mirror compaction for already-ingested Claude Code/Codex sessions.

저자: JunyoungJung
작성일: 2026-07-03
"""
from __future__ import annotations

import base64
import gzip
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from synapse_memory.storage.l0 import L0_FILE_MODE, ensure_secure_dir
from synapse_memory.wiki.offsets import load_offsets, save_offsets
from synapse_memory.wiki.rawdoc import (
    SUPPORTED_SOURCES,
    _extract_text,
    default_source_root,
)
from synapse_memory.wiki.watermark import load_watermark

SIDECAR_SUFFIX = ".toolio.jsonl.gz"
_SIDECAR_KIND = "synapse-raw-compact"
_SIDECAR_VERSION = 1
_CODEX_MESSAGE_ROLES = {"assistant", "user"}


@dataclass(frozen=True)
class DroppedLine:
    line_index: int
    raw: bytes


@dataclass(frozen=True)
class CompactBytesResult:
    original_size: int
    kept: bytes
    dropped: tuple[DroppedLine, ...]
    total_lines: int
    kept_lines: int

    @property
    def kept_size(self) -> int:
        return len(self.kept)

    @property
    def dropped_size(self) -> int:
        return self.original_size - self.kept_size

    @property
    def dropped_lines(self) -> int:
        return len(self.dropped)


@dataclass(frozen=True)
class CompactFileResult:
    ref: str
    path: Path
    status: Literal[
        "compacted",
        "dry_run",
        "already_compacted",
        "rehydrated",
        "rehydrate_dry_run",
        "skipped",
        "aborted",
    ]
    original_size: int = 0
    kept_size: int = 0
    dropped_size: int = 0
    kept_lines: int = 0
    dropped_lines: int = 0
    reason: str = ""
    sidecar_path: Path | None = None


@dataclass(frozen=True)
class CompactSourceResult:
    source: str
    dry_run: bool
    rehydrate: bool
    files_seen: int = 0
    files_eligible: int = 0
    files_changed: int = 0
    files_skipped: int = 0
    files_aborted: int = 0
    bytes_reclaimable: int = 0
    results: tuple[CompactFileResult, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


def _decode_event(raw_line: bytes) -> dict[str, object] | None:
    stripped = raw_line.strip()
    if not stripped:
        return None
    try:
        value = json.loads(stripped.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def keep_line(
    source: str,
    event: dict[str, object],
    *,
    line_index: int,
    claude_cwd_seen: bool = False,
) -> bool:
    """Return True only for lines read by live consumers."""
    if source == "claude-code":
        if _extract_text(event):
            return True
        return line_index < 30 and not claude_cwd_seen and "cwd" in event
    if source == "codex":
        etype = event.get("type")
        payload = event.get("payload")
        if etype == "session_meta":
            return True
        if not isinstance(payload, dict):
            return False
        if etype == "event_msg" and payload.get("type") == "user_message":
            return True
        return (
            etype == "response_item"
            and payload.get("type") == "message"
            and payload.get("role") in _CODEX_MESSAGE_ROLES
        )
    return False


def compact_bytes(source: str, data: bytes) -> CompactBytesResult:
    kept: list[bytes] = []
    dropped: list[DroppedLine] = []
    claude_cwd_seen = False
    lines = data.splitlines(keepends=True)
    for line_index, raw_line in enumerate(lines):
        event = _decode_event(raw_line)
        should_keep = (
            event is not None
            and keep_line(
                source,
                event,
                line_index=line_index,
                claude_cwd_seen=claude_cwd_seen,
            )
        )
        if event is not None and source == "claude-code" and "cwd" in event:
            claude_cwd_seen = True
        if should_keep:
            kept.append(raw_line)
        else:
            dropped.append(DroppedLine(line_index=line_index, raw=raw_line))
    return CompactBytesResult(
        original_size=len(data),
        kept=b"".join(kept),
        dropped=tuple(dropped),
        total_lines=len(lines),
        kept_lines=len(kept),
    )


def compact_mirror_source(
    source: str,
    *,
    root: Path | None = None,
    watermark_path: Path | None = None,
    apply: bool = False,
    rehydrate: bool = False,
) -> CompactSourceResult:
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"미지원 source: {source!r}")
    base = (root or default_source_root(source)).expanduser().resolve()
    if not base.is_dir():
        return CompactSourceResult(source=source, dry_run=not apply, rehydrate=rehydrate)

    watermark = load_watermark(source, path=watermark_path)
    watermark_us = _iso_to_us(watermark) if watermark else None
    offsets = load_offsets(path=watermark_path)

    results: list[CompactFileResult] = []
    errors: list[str] = []
    changed = skipped = aborted = eligible = reclaimable = 0
    targets = list(_iter_target_jsonl(source, base))

    for path in targets:
        ref = f"{source}:{path.relative_to(base).as_posix()}"
        try:
            if rehydrate:
                item = _rehydrate_file(
                    source,
                    ref,
                    path,
                    apply=apply,
                    watermark_path=watermark_path,
                )
            else:
                item = _compact_file(
                    source,
                    ref,
                    path,
                    watermark_us=watermark_us,
                    offset=offsets.get(ref),
                    apply=apply,
                    watermark_path=watermark_path,
                )
        except OSError as exc:
            item = CompactFileResult(ref=ref, path=path, status="aborted", reason=str(exc))
        results.append(item)
        if item.status in {"compacted", "dry_run", "already_compacted", "rehydrated", "rehydrate_dry_run"}:
            eligible += 1
        if item.status in {"compacted", "rehydrated"}:
            changed += 1
        elif item.status == "skipped":
            skipped += 1
        elif item.status == "aborted":
            aborted += 1
            errors.append(f"{ref}: {item.reason}")
        reclaimable += item.dropped_size

    return CompactSourceResult(
        source=source,
        dry_run=not apply,
        rehydrate=rehydrate,
        files_seen=len(targets),
        files_eligible=eligible,
        files_changed=changed,
        files_skipped=skipped,
        files_aborted=aborted,
        bytes_reclaimable=reclaimable,
        results=tuple(results),
        errors=tuple(errors),
    )


def rehydrate(
    source: str,
    *,
    root: Path | None = None,
    watermark_path: Path | None = None,
    apply: bool = False,
) -> CompactSourceResult:
    return compact_mirror_source(
        source,
        root=root,
        watermark_path=watermark_path,
        apply=apply,
        rehydrate=True,
    )


def _compact_file(
    source: str,
    ref: str,
    path: Path,
    *,
    watermark_us: int | None,
    offset: int | None,
    apply: bool,
    watermark_path: Path | None,
) -> CompactFileResult:
    stat_before = path.stat()
    current_size = stat_before.st_size
    sidecar = _sidecar_path(path)
    if sidecar.exists():
        header = _read_sidecar_header(sidecar)
        if _as_int(header.get("kept_size"), -1) == current_size:
            if apply:
                save_offsets({ref: current_size}, path=watermark_path)
            return CompactFileResult(
                ref=ref,
                path=path,
                status="already_compacted",
                original_size=_as_int(header.get("original_size"), current_size),
                kept_size=current_size,
                dropped_size=_as_int(header.get("dropped_size"), 0),
                kept_lines=_as_int(header.get("kept_lines"), 0),
                dropped_lines=_as_int(header.get("dropped_lines"), 0),
                sidecar_path=sidecar,
            )
        sidecar.unlink()

    if watermark_us is None:
        return CompactFileResult(ref=ref, path=path, status="skipped", reason="watermark 없음")
    mtime_us = int(stat_before.st_mtime * 1_000_000)
    if mtime_us > watermark_us:
        return CompactFileResult(ref=ref, path=path, status="skipped", reason="watermark 이후 mtime")
    if offset != current_size:
        return CompactFileResult(
            ref=ref,
            path=path,
            status="skipped",
            reason=f"offset mismatch: offset={offset} size={current_size}",
        )

    data = path.read_bytes()
    compacted = compact_bytes(source, data)
    if compacted.dropped_size == 0:
        if apply:
            save_offsets({ref: current_size}, path=watermark_path)
        return CompactFileResult(
            ref=ref,
            path=path,
            status="already_compacted",
            original_size=current_size,
            kept_size=current_size,
            sidecar_path=sidecar,
        )
    if not apply:
        return CompactFileResult(
            ref=ref,
            path=path,
            status="dry_run",
            original_size=compacted.original_size,
            kept_size=compacted.kept_size,
            dropped_size=compacted.dropped_size,
            kept_lines=compacted.kept_lines,
            dropped_lines=compacted.dropped_lines,
            sidecar_path=sidecar,
        )

    header = {
        "kind": _SIDECAR_KIND,
        "version": _SIDECAR_VERSION,
        "source": source,
        "ref": ref,
        "original_size": compacted.original_size,
        "kept_size": compacted.kept_size,
        "dropped_size": compacted.dropped_size,
        "line_count": compacted.total_lines,
        "kept_lines": compacted.kept_lines,
        "dropped_lines": compacted.dropped_lines,
        "mtime_ns": stat_before.st_mtime_ns,
    }
    temp = _temp_path(path, ".compact")
    sidecar_tmp = _temp_path(sidecar, ".tmp")
    try:
        _write_bytes_secure(temp, compacted.kept)
        os.utime(temp, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))
        _write_sidecar(sidecar_tmp, header, compacted.dropped)
        os.replace(sidecar_tmp, sidecar)
        stat_latest = path.stat()
        if (
            stat_latest.st_size != current_size
            or stat_latest.st_mtime_ns != stat_before.st_mtime_ns
        ):
            return CompactFileResult(ref=ref, path=path, status="aborted", reason="mirror changed")
        os.replace(temp, path)
        save_offsets({ref: compacted.kept_size}, path=watermark_path)
    finally:
        temp.unlink(missing_ok=True)
        sidecar_tmp.unlink(missing_ok=True)

    return CompactFileResult(
        ref=ref,
        path=path,
        status="compacted",
        original_size=compacted.original_size,
        kept_size=compacted.kept_size,
        dropped_size=compacted.dropped_size,
        kept_lines=compacted.kept_lines,
        dropped_lines=compacted.dropped_lines,
        sidecar_path=sidecar,
    )


def _rehydrate_file(
    source: str,
    ref: str,
    path: Path,
    *,
    apply: bool,
    watermark_path: Path | None,
) -> CompactFileResult:
    sidecar = _sidecar_path(path)
    if not sidecar.exists():
        return CompactFileResult(ref=ref, path=path, status="skipped", reason="sidecar 없음")
    header, dropped = _read_sidecar(sidecar)
    if header.get("kind") != _SIDECAR_KIND or header.get("ref") != ref:
        return CompactFileResult(ref=ref, path=path, status="aborted", reason="sidecar 불일치")
    if not apply:
        return CompactFileResult(
            ref=ref,
            path=path,
            status="rehydrate_dry_run",
            original_size=_as_int(header.get("original_size"), 0),
            kept_size=_as_int(header.get("kept_size"), 0),
            dropped_size=_as_int(header.get("dropped_size"), 0),
            kept_lines=_as_int(header.get("kept_lines"), 0),
            dropped_lines=_as_int(header.get("dropped_lines"), 0),
            sidecar_path=sidecar,
        )

    kept = path.read_bytes().splitlines(keepends=True)
    line_count = _as_int(header.get("line_count"), 0)
    stat_before = path.stat()
    temp = _temp_path(path, ".rehydrate")
    try:
        restored_size = _write_lines_secure(
            temp, _iter_merged_lines(kept, dropped, line_count=line_count)
        )
        mtime_ns = _as_int(header.get("mtime_ns"), stat_before.st_mtime_ns)
        os.utime(temp, ns=(stat_before.st_atime_ns, mtime_ns))
        os.replace(temp, path)
        sidecar.unlink(missing_ok=True)
        save_offsets({ref: restored_size}, path=watermark_path)
    finally:
        temp.unlink(missing_ok=True)

    return CompactFileResult(
        ref=ref,
        path=path,
        status="rehydrated",
        original_size=restored_size,
        kept_size=_as_int(header.get("kept_size"), 0),
        dropped_size=_as_int(header.get("dropped_size"), 0),
        kept_lines=_as_int(header.get("kept_lines"), 0),
        dropped_lines=_as_int(header.get("dropped_lines"), 0),
        sidecar_path=sidecar,
    )


def _iter_target_jsonl(source: str, base: Path) -> tuple[Path, ...]:
    if source == "claude-code":
        paths = (base / "projects").rglob("*.jsonl")
    elif source == "codex":
        paths = (base / "sessions").rglob("*.jsonl")
    else:
        return ()
    return tuple(
        sorted(
            p
            for p in paths
            if p.is_file() and p.name not in {"history.jsonl", "session_index.jsonl"}
        )
    )


def _iso_to_us(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000)


def _as_int(value: object, default: int) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + SIDECAR_SUFFIX)


def _temp_path(path: Path, suffix: str) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}{suffix}")


def _write_bytes_secure(path: Path, data: bytes) -> None:
    ensure_secure_dir(path.parent)
    path.write_bytes(data)
    os.chmod(path, L0_FILE_MODE)


def _write_sidecar(path: Path, header: dict[str, Any], dropped: tuple[DroppedLine, ...]) -> None:
    ensure_secure_dir(path.parent)
    with gzip.open(path, "wb") as handle:
        handle.write(json.dumps(header, separators=(",", ":")).encode("utf-8") + b"\n")
        for item in dropped:
            record = {
                "line": item.line_index,
                "raw_b64": base64.b64encode(item.raw).decode("ascii"),
            }
            handle.write(json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n")
    os.chmod(path, L0_FILE_MODE)


def _read_sidecar_header(path: Path) -> dict[str, object]:
    with gzip.open(path, "rb") as handle:
        line = handle.readline()
    value = json.loads(line.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"sidecar header invalid: {path}")
    return value


def _read_sidecar(path: Path) -> tuple[dict[str, object], dict[int, bytes]]:
    dropped: dict[int, bytes] = {}
    with gzip.open(path, "rb") as handle:
        header_line = handle.readline()
        header = json.loads(header_line.decode("utf-8"))
        if not isinstance(header, dict):
            raise ValueError(f"sidecar header invalid: {path}")
        for raw_record in handle:
            record = json.loads(raw_record.decode("utf-8"))
            if isinstance(record, dict):
                dropped[int(record["line"])] = base64.b64decode(str(record["raw_b64"]))
    return header, dropped


def _iter_merged_lines(
    kept_lines: list[bytes],
    dropped: dict[int, bytes],
    *,
    line_count: int,
) -> Iterator[bytes]:
    """dropped(제거됐던 줄)+kept(보존된 줄)를 원래 line 순서로 재병합해 yield.

    전체 결과를 메모리에 buffer하지 않고 줄 단위로 흘려보낸다 — rehydrate가 원본
    크기의 추가 복사본(merged 리스트 + join 버퍼)을 들지 않게 한다.
    """
    kept_iter = iter(kept_lines)
    for line_index in range(line_count):
        if line_index in dropped:
            yield dropped[line_index]
        else:
            yield next(kept_iter)
    yield from kept_iter


def _write_lines_secure(path: Path, lines: Iterator[bytes]) -> int:
    """줄 iterator를 안전 권한(0600) 파일로 증분 기록. 총 바이트 수 반환."""
    ensure_secure_dir(path.parent)
    total = 0
    with path.open("wb") as handle:
        for chunk in lines:
            handle.write(chunk)
            total += len(chunk)
    os.chmod(path, L0_FILE_MODE)
    return total
