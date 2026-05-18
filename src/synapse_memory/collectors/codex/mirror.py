"""Codex CLI 로그 mirror — incremental tail.

소스
----
- ``~/.codex/history.jsonl`` (사용자 입력 라인)
- ``~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl`` (세션별 rollout)

대상: ``~/.synapse/private/raw/codex/`` 아래 동일 상대 경로로 mirror.

claude_code/mirror.py 와 동일한 핵심 보장 (partial-line safe, idempotent,
rotation safe, atomic offset)을 그대로 활용한다. JSONL tail-append 로직 자체는
:func:`synapse_memory.collectors.claude_code.mirror.mirror_jsonl`을 재사용한다.

제외
----
- ``~/.codex/session_index.jsonl`` — 메타 인덱스(매번 rewrite 가능, sessions 의
  ground truth 가 sessions/*.jsonl). 노이즈 회피 목적.
- ``~/.codex/{logs_2.sqlite,state_5.sqlite,auth.json,config.toml,...}`` —
  JSONL 아닌 파일은 자동 제외.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import os
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

DEFAULT_CODEX_HOME = Path.home() / ".codex"
SUBPATH = Path("raw") / "codex"

__all__ = [
    "DEFAULT_CODEX_HOME",
    "OFFSETS_DIR",
    "SUBPATH",
    "CollectStats",
    "FileMirrorResult",
    "collect_codex",
    "mirror_jsonl",
]


# ---------------------------------------------------------------------------
# 수집 대상 enumerate
# ---------------------------------------------------------------------------


def _enumerate_jsonl(codex_home: Path) -> list[Path]:
    """수집 대상 jsonl 파일 목록.

    포함:
        ~/.codex/history.jsonl
        ~/.codex/sessions/<YYYY>/<MM>/<DD>/*.jsonl

    제외:
        ~/.codex/session_index.jsonl (매번 rewrite 가능, 인덱스만)
        ~/.codex/{logs,backups,prompts,plugins,...}/* (JSONL 외 또는 노이즈)
    """
    targets: list[Path] = []

    history = codex_home / "history.jsonl"
    if history.is_file():
        targets.append(history)

    sessions = codex_home / "sessions"
    if sessions.is_dir():
        for jsonl in sorted(sessions.rglob("*.jsonl")):
            if jsonl.is_file():
                targets.append(jsonl)

    return targets


def _dst_for(src: Path, codex_home: Path, dst_root: Path) -> Path:
    """src 위치를 dst_root 아래 거울 경로로 변환."""
    rel = src.relative_to(codex_home)
    return dst_root / rel


def _offset_path_for(src: Path, codex_home: Path, dst_root: Path) -> Path:
    """offset 메타 파일 경로. ``<dst_root>/.offsets/<rel-with-__>.offset``."""
    rel = src.relative_to(codex_home)
    flat = str(rel).replace(os.sep, "__").replace("/", "__")
    return dst_root / OFFSETS_DIR / f"{flat}.offset"


# ---------------------------------------------------------------------------
# 전체 수집
# ---------------------------------------------------------------------------


def collect_codex(
    *,
    codex_home: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Codex CLI 데이터 1회 수집 (incremental).

    Args:
        codex_home: ~/.codex (기본). 테스트에서 override.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/codex``).

    Returns:
        CollectStats — 처리 통계. ``codex_home`` 미존재 시 errors 에 기록 후 반환.
    """
    codex_home = (codex_home or DEFAULT_CODEX_HOME).expanduser().resolve()
    dst_root = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not codex_home.is_dir():
        stats.errors.append((codex_home, f"Codex home 없음: {codex_home}"))
        return stats

    if dst_root.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()

    ensure_secure_dir(dst_root)
    ensure_secure_dir(dst_root / OFFSETS_DIR)

    for src in _enumerate_jsonl(codex_home):
        stats.files_scanned += 1
        try:
            if src.stat().st_size == 0:
                stats.skipped_empty += 1
                continue
            dst = _dst_for(src, codex_home, dst_root)
            offset = _offset_path_for(src, codex_home, dst_root)
            result = mirror_jsonl(src, dst, offset)
            if result.truncated_reset:
                stats.truncations += 1
            if result.bytes_added > 0:
                stats.files_mirrored += 1
                stats.bytes_added += result.bytes_added
        except OSError as exc:
            stats.errors.append((src, str(exc)))

    return stats
