"""Shell history mirror — incremental tail.

소스
----
- ``~/.zsh_history``  (zsh, EXTENDED_HISTORY 옵션 시 타임스탬프 포함)
- ``~/.bash_history`` (bash, 존재 시만)

대상: ``~/.synapse/private/raw/shell-history/`` 아래 동일 파일명으로 mirror.

``claude_code/mirror.py`` 의 :func:`mirror_jsonl` 을 재사용한다 — 한 줄 = 한
명령으로 본 형식이 JSONL 과 동일한 newline-terminated record 특성을 갖기
때문이다. partial-line / rotation / atomic offset 보장 동일.

zsh 의 ``HIST_REDUCE_BLANKS`` / ``HIST_IGNORE_DUPS`` 같은 옵션은 source 측에서
처리되므로 mirror 는 단순 byte-copy. 형식 파싱은 후속 classify 단계에서.

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

DEFAULT_ZSH_HISTORY = Path.home() / ".zsh_history"
DEFAULT_BASH_HISTORY = Path.home() / ".bash_history"
SUBPATH = Path("raw") / "shell-history"

__all__ = [
    "DEFAULT_BASH_HISTORY",
    "DEFAULT_ZSH_HISTORY",
    "OFFSETS_DIR",
    "SUBPATH",
    "CollectStats",
    "FileMirrorResult",
    "collect_shell_history",
]


def _enumerate_history_files(
    zsh_history: Path,
    bash_history: Path,
) -> list[tuple[str, Path]]:
    """수집 대상 (logical-name, src) 쌍 목록. 존재하는 것만."""
    out: list[tuple[str, Path]] = []
    if zsh_history.is_file():
        out.append(("zsh_history", zsh_history))
    if bash_history.is_file():
        out.append(("bash_history", bash_history))
    return out


def _dst_for(logical_name: str, dst_root: Path) -> Path:
    return dst_root / logical_name


def _offset_path_for(logical_name: str, dst_root: Path) -> Path:
    return dst_root / OFFSETS_DIR / f"{logical_name}.offset"


def collect_shell_history(
    *,
    zsh_history: Path | None = None,
    bash_history: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Shell history 1회 수집 (incremental).

    Args:
        zsh_history: ``~/.zsh_history`` 기본. 테스트에서 override.
        bash_history: ``~/.bash_history`` 기본.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/shell-history``).

    Returns:
        CollectStats — 처리 통계. 두 파일 모두 미존재 시 errors 비어있고
        files_scanned == 0 (조용한 skip — 정상 상태).
    """
    zsh = (zsh_history or DEFAULT_ZSH_HISTORY).expanduser().resolve()
    bash = (bash_history or DEFAULT_BASH_HISTORY).expanduser().resolve()
    dst_root = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    targets = _enumerate_history_files(zsh, bash)
    if not targets:
        return stats  # 어느 셸도 안 쓰는 사용자 — 정상

    if dst_root.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()

    ensure_secure_dir(dst_root)
    ensure_secure_dir(dst_root / OFFSETS_DIR)

    for logical_name, src in targets:
        stats.files_scanned += 1
        try:
            if src.stat().st_size == 0:
                stats.skipped_empty += 1
                continue
            dst = _dst_for(logical_name, dst_root)
            offset = _offset_path_for(logical_name, dst_root)
            result = mirror_jsonl(src, dst, offset)
            if result.truncated_reset:
                stats.truncations += 1
            if result.bytes_added > 0:
                stats.files_mirrored += 1
                stats.bytes_added += result.bytes_added
        except OSError as exc:
            stats.errors.append((src, str(exc)))

    return stats
