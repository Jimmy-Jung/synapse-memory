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

SUPPORTED_SOURCES = ("claude-code", "codex")


@dataclass(frozen=True)
class RawDoc:
    """ingest 단위 — 한 대화 세션의 평문 텍스트."""

    source: str
    ref: str          # "claude-code:projects/demo/sess1.jsonl"
    text: str
    mtime_iso: str    # 파일 수정 시각 (watermark 갱신용)


def default_source_root(source: str) -> Path:
    return l0_root() / "raw" / source


def _extract_text(event: dict[str, object]) -> str:
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


def _join_content_text(content: object) -> str:
    """codex message content 블록 리스트에서 text를 이어붙인다.

    블록 type은 ``output_text``(assistant) / ``input_text``(user/developer) 등 다양하나
    모두 ``text`` 키를 가진다. 문자열 content도 허용.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return ""


def _extract_text_codex(event: dict[str, object]) -> str:
    """codex rollout jsonl 이벤트에서 사람이 읽는 대화 텍스트 추출 (best-effort).

    codex 스키마는 ``{"type": "...", "payload": {...}}`` 래퍼. 채널별 특성:

    - 사용자 턴: ``event_msg/user_message`` → ``payload.message`` (평문, 깨끗 — AGENTS.md
      주입/보일러플레이트 없음). ``response_item/message(role=user)``는 지시문 주입 노이즈라 제외.
    - 어시스턴트 턴: ``response_item/message(role=assistant)`` → ``content[].text`` 전체.
      ``event_msg/agent_message``는 **첫 구조블록 전까지 잘린 도입부**(긴 turn의 본문 대부분
      유실)라 사용하지 않는다.
    - 제외: ``role=developer`` 보일러플레이트, ``reasoning``/``function_call``/tool 노이즈,
      ``token_count`` 등.
    """
    etype = event.get("type")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ""

    if etype == "event_msg" and payload.get("type") == "user_message":
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return f"User: {message}"
        return ""

    if (
        etype == "response_item"
        and payload.get("type") == "message"
        and payload.get("role") == "assistant"
    ):
        text = _join_content_text(payload.get("content"))
        if text.strip():
            return f"Assistant: {text}"
        return ""

    return ""


_SOURCE_EXTRACTORS = {
    "codex": _extract_text_codex,
}


def _file_text(path: Path, source: str) -> str:
    extract = _SOURCE_EXTRACTORS.get(source, _extract_text)
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
            text = extract(event)
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
    """source의 새 RawDoc을 **mtime 오름차순**으로 **lazy yield** (mtime > since).

    파일 경로+stat 목록은 정렬 위해 1회 materialize하지만, 파일 본문(``_file_text``)은
    yield 시점에 1개씩만 읽는다 — 호출측이 ``itertools.islice``로 N개만 소비하면 N개
    본문만 로드된다(020 메모리 천장 유지).

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
    # mtime은 **마이크로초 정수**로 다룬다. 과거 초 단위 절삭은 같은 초에 미러된 파일
    # 수백 개의 mtime을 동일 값으로 뭉개, watermark(=최대 mtime) + limit 조합에서
    # 같은 초의 나머지 파일을 영구 skip시키는 데이터 손실을 일으켰다. 마이크로초 정수는
    # isoformat(timespec="microseconds") ↔ fromisoformat 라운드트립이 정확해 재처리도 없다.
    since_us = (
        int(datetime.fromisoformat(since).timestamp() * 1_000_000)
        if since
        else None
    )
    now_s = now if now is not None else time.time()
    settled_before_us = (
        int((now_s - min_age_seconds) * 1_000_000)
        if min_age_seconds is not None
        else None
    )
    # (mtime, path)순으로 정렬해 watermark가 시간순으로 단조 증가하도록 한다. 경로순
    # 정렬은 mtime 순서와 어긋나 limit 경계에서 낮은 mtime 파일을 건너뛸 수 있었다.
    # stat은 여기서 1회씩(전체 경로), 본문(_file_text)은 yield 시점에 1개씩만 읽는다
    # (islice로 N개만 소비하면 N개 본문만 로드 — 020 메모리 천장 유지).
    entries: list[tuple[int, str, Path]] = []
    for path in base.rglob("*.jsonl"):
        try:
            mtime_us = int(path.stat().st_mtime * 1_000_000)
        except OSError:
            continue
        entries.append((mtime_us, path.as_posix(), path))
    entries.sort(key=lambda e: (e[0], e[1]))
    for mtime_us, _posix, path in entries:
        if since_us is not None and mtime_us <= since_us:
            continue
        # settled 필터: 너무 최근에 변경된 파일(진행 중 대화)은 건너뛴다.
        if settled_before_us is not None and mtime_us > settled_before_us:
            continue
        text = _file_text(path, source)
        if not text:
            continue
        rel = path.relative_to(base).as_posix()
        yield RawDoc(
            source=source,
            ref=f"{source}:{rel}",
            text=text,
            mtime_iso=datetime.fromtimestamp(mtime_us / 1_000_000).isoformat(
                timespec="microseconds"
            ),
        )
