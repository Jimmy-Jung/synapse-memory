# src/synapse_memory/wiki/rawdoc.py
"""raw 소스 → RawDoc. P1a는 claude-code 미러 jsonl만.

각 jsonl 파일 = 한 대화 세션 = 한 RawDoc. mtime이 watermark(since) 이후인 파일만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

SUPPORTED_SOURCES = ("claude-code",)


@dataclass(frozen=True)
class RawDoc:
    """ingest 단위 — 한 대화 세션의 평문 텍스트."""

    source: str
    ref: str          # "claude-code:projects/demo/sess1.jsonl"
    text: str
    mtime_iso: str    # 파일 수정 시각 (watermark 갱신용)


def default_source_root(source: str) -> Path:
    return l0_root() / "raw" / source


def _extract_text(event: dict) -> str:
    """claude-code jsonl 이벤트에서 사람이 읽는 텍스트 추출 (best-effort)."""
    msg = event.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return ""


def _file_text(path: Path) -> str:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            text = _extract_text(event)
            if text:
                lines.append(text)
    return "\n\n".join(lines)


def iter_new_raw(
    source: str,
    *,
    since: str | None,
    root: Path | None = None,
    min_age_seconds: float | None = None,
    now: float | None = None,
) -> Iterator[RawDoc]:
    """source의 새 RawDoc을 ref 정렬 순서로 **lazy yield** (mtime > since).

    020: 리스트 materialize 대신 제너레이터 — 호출측이 ``itertools.islice``로 N개만
    소비하면 그 N개 파일만 읽어들인다(backlog 전체를 메모리에 올리지 않음). 파일
    본문(``_file_text``)은 yield 시점에 1개씩만 읽는다.

    ``min_age_seconds``가 주어지면 ``(now or time.time()) - min_age_seconds``보다
    최근에 수정된 파일(=진행 중)은 건너뛴다. ``None``이면 기존 동작 그대로.

    Raises:
        ValueError: 미지원 source (첫 반복 시점에 발생 — 제너레이터 lazy 평가).
    """
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"미지원 source: {source!r}")
    base = (root or default_source_root(source)).expanduser()
    if not base.is_dir():
        return
    since_ts = datetime.fromisoformat(since).timestamp() if since else None
    settled_before = (
        (now if now is not None else time.time()) - min_age_seconds
        if min_age_seconds is not None
        else None
    )
    for path in sorted(base.rglob("*.jsonl")):
        # 워터마크는 초 단위(timespec="seconds")로 저장되므로 비교도 초로 절삭해야
        # 동일 파일이 재처리되지 않는다.
        mtime = float(int(path.stat().st_mtime))
        if since_ts is not None and mtime <= since_ts:
            continue
        # settled 필터: 너무 최근에 변경된 파일(진행 중 대화)은 건너뛴다.
        if settled_before is not None and mtime > settled_before:
            continue
        text = _file_text(path)
        if not text:
            continue
        rel = path.relative_to(base).as_posix()
        yield RawDoc(
            source=source,
            ref=f"{source}:{rel}",
            text=text,
            mtime_iso=datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        )
