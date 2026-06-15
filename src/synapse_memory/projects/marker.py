"""Marker block injection / replacement for project AGENTS.md / CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "MARKER_END",
    "MARKER_START",
    "MarkerParseError",
    "extract_block",
    "inject_or_replace",
]


MARKER_START = "<!-- SYNAPSE-MEMORY START -->"
MARKER_END = "<!-- SYNAPSE-MEMORY END -->"


class MarkerParseError(ValueError):
    """marker가 잘못된 상태 (START 또는 END 한쪽만 존재)."""


def extract_block(file: Path) -> str | None:
    """marker 사이 본문 반환. 없으면 None, unclosed면 MarkerParseError."""
    if not file.is_file():
        return None
    text = file.read_text(encoding="utf-8")
    start_idx = text.find(MARKER_START)
    end_idx = text.find(MARKER_END)
    if start_idx == -1 and end_idx == -1:
        return None
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise MarkerParseError(
            f"{file}: marker 구조가 잘못됐습니다 "
            f"(START={start_idx != -1}, END={end_idx != -1})"
        )
    body_start = start_idx + len(MARKER_START)
    return text[body_start:end_idx]


def _wrap(body: str) -> str:
    body_normalized = body if body.endswith("\n") else body + "\n"
    if not body_normalized.startswith("\n"):
        body_normalized = "\n" + body_normalized
    return f"{MARKER_START}{body_normalized}{MARKER_END}\n"


def inject_or_replace(file: Path, body: str) -> tuple[bool, str | None]:
    """marker로 감싼 body를 file에 주입. 신규/append/교체 자동 분기.

    Returns:
        (changed, previous_body):
            changed — 파일이 실제로 바뀌었으면 True
            previous_body — marker가 이미 있어 교체된 경우 이전 body, 아니면 None
    """
    wrapped = _wrap(body)

    if not file.is_file():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(wrapped, encoding="utf-8")
        return True, None

    text = file.read_text(encoding="utf-8")
    start_idx = text.find(MARKER_START)
    end_idx = text.find(MARKER_END)

    if start_idx == -1 and end_idx == -1:
        new_text = text
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += "\n" + wrapped
        file.write_text(new_text, encoding="utf-8")
        return True, None

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise MarkerParseError(
            f"{file}: marker 구조가 잘못됐습니다 "
            f"(START={start_idx != -1}, END={end_idx != -1})"
        )

    previous = text[start_idx + len(MARKER_START) : end_idx]
    suffix = text[end_idx + len(MARKER_END) :]
    inner = wrapped.rstrip("\n")
    if suffix.startswith("\n") or not suffix:
        new_text = text[:start_idx] + inner + suffix
    else:
        new_text = text[:start_idx] + inner + "\n" + suffix
    if new_text == text:
        return False, previous
    file.write_text(new_text, encoding="utf-8")
    return True, previous
