"""Aider → L0 mirror.

소스:
    ``~/.aider.chat.history.md`` — markdown 대화 기록
    ``~/.aider.input.history``   — 사용자 입력 history

대상: ``~/.synapse/private/raw/aider/`` 아래 동일 파일명.

:func:`mirror_jsonl` 재사용 — 한 줄 = 한 record. partial-line / rotation /
atomic offset 보장 동일.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.collectors.claude_code.mirror import (
    OFFSETS_DIR,
    CollectStats,
    FileMirrorResult,
    mirror_jsonl,
)
from synapse_memory.storage.l0 import (
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_CHAT_HISTORY = Path.home() / ".aider.chat.history.md"
DEFAULT_INPUT_HISTORY = Path.home() / ".aider.input.history"
SUBPATH = Path("raw") / "aider"

__all__ = [
    "DEFAULT_CHAT_HISTORY",
    "DEFAULT_INPUT_HISTORY",
    "OFFSETS_DIR",
    "SUBPATH",
    "CollectStats",
    "FileMirrorResult",
    "collect_aider",
]


def _enumerate(
    chat_history: Path, input_history: Path
) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    if chat_history.is_file():
        out.append(("chat.history.md", chat_history))
    if input_history.is_file():
        out.append(("input.history", input_history))
    return out


def collect_aider(
    *,
    chat_history: Path | None = None,
    input_history: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Aider 데이터 1회 수집 (incremental).

    Args:
        chat_history: ``~/.aider.chat.history.md`` 기본.
        input_history: ``~/.aider.input.history`` 기본.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/aider``).

    Returns:
        CollectStats — 처리 통계. 둘 다 미존재 시 errors 없이 빈 통계 반환
        (Aider 미사용 사용자 — 정상).
    """
    chat = (chat_history or DEFAULT_CHAT_HISTORY).expanduser().resolve()
    inp = (input_history or DEFAULT_INPUT_HISTORY).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    targets = _enumerate(chat, inp)
    if not targets:
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / OFFSETS_DIR)

    for logical_name, src in targets:
        stats.files_scanned += 1
        try:
            if src.stat().st_size == 0:
                stats.skipped_empty += 1
                continue
            dst_file = dst / logical_name
            offset = dst / OFFSETS_DIR / f"{logical_name}.offset"
            result = mirror_jsonl(src, dst_file, offset)
            if result.truncated_reset:
                stats.truncations += 1
            if result.bytes_added > 0:
                stats.files_mirrored += 1
                stats.bytes_added += result.bytes_added
        except OSError as exc:
            stats.errors.append((src, str(exc)))

    return stats
