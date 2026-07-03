"""Obsidian vault → L0 mirror.

핵심 차이 (Claude Code mirror 대비)
-----------------------------------
- 단위가 jsonl 라인이 아니라 .md **파일 전체**.
- partial-line 안전성 불필요 — md는 atomic 저장.
- 변경 감지: mtime + size + sha256 3-tier (가장 싼 것부터).
- 삭제된 파일은 mirror에 그대로 남겨둠 (실수 보호 — W2 후 정책 재검토).

vault 경로
----------
``~/Library/Mobile Documents/iCloud~md~obsidian/Documents`` 가 기본.
``SYNAPSE_OBSIDIAN_VAULT`` 환경변수로 override 가능.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.collectors._filestate import (
    FileState,
    file_sha256 as _file_sha256,
    load_states as _load_states,
    save_states_atomic as _save_states_atomic,
)
from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_VAULT_PATH = (
    Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
)
ENV_VAR_VAULT = "SYNAPSE_OBSIDIAN_VAULT"
SUBPATH = Path("raw") / "obsidian"
META_DIR = ".meta"
STATES_FILE = "states.json"

# vault CLAUDE.md 원칙: AI 메모리는 mirror 안 함 (순환 방지),
# Attachments/binary와 마이그레이션 스냅샷도 제외.
# plugin config 디렉토리(.claude, .codex 등)도 PII 가치 낮음 + 토큰 가능성.
EXCLUDED_DIRS: tuple[str, ...] = (".obsidian", ".trash", ".claude", ".codex")
# 부분 매칭 — 파일 경로에 포함되면 제외.
# iCloud sync-conflict 파일 패턴 — ``Note (sync-conflict 2026-...)`` 또는
# ``.sync-conflict-...`` 모두 커버하기 위해 점 없이 매칭.
EXCLUDED_SUBSTRINGS: tuple[str, ...] = (
    "sync-conflict",
)

INCLUDED_EXT = ".md"


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------


@dataclass
class CollectStats:
    files_scanned: int = 0
    files_mirrored: int = 0     # 실제 copy된 파일
    files_unchanged: int = 0    # mtime/size 또는 hash 일치로 skip
    files_skipped_by_cutoff: int = 0  # since_days cutoff 로 skip (--quick 모드)
    bytes_added: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self) -> str:
        cutoff = (
            f" cutoff_skip={self.files_skipped_by_cutoff}"
            if self.files_skipped_by_cutoff
            else ""
        )
        return (
            f"scanned={self.files_scanned} mirrored={self.files_mirrored} "
            f"unchanged={self.files_unchanged}{cutoff} "
            f"bytes+={self.bytes_added} errors={len(self.errors)}"
        )


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------


def get_vault_path() -> Path:
    """env var 우선, 없으면 기본 iCloud Obsidian 경로."""
    override = os.environ.get(ENV_VAR_VAULT)
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_VAULT_PATH


def _normalized_prefix(path: str) -> str:
    return path.strip().strip("/")


def _is_excluded(rel_path: Path) -> bool:
    """exclude 패턴 매칭."""
    from synapse_memory.config import get_config

    rel_str = rel_path.as_posix()
    folders = get_config().vault_folders
    wiki = folders.wiki
    excluded_dirs = (
        folders.system.ai.root,
        folders.system.attachments,
        folders.system.migration,
        wiki.projects,
        wiki.companies,
        wiki.people,
        wiki.concepts,
        wiki.profile,
        wiki.insights,
        *EXCLUDED_DIRS,
    )
    for ex in excluded_dirs:
        ex = _normalized_prefix(ex)
        if not ex:
            continue
        if rel_str == ex or rel_str.startswith(ex + "/"):
            return True
    return any(sub in rel_str for sub in EXCLUDED_SUBSTRINGS)


def _enumerate_md(vault: Path) -> list[Path]:
    """vault 안 .md 파일 목록 (exclude 적용)."""
    targets: list[Path] = []
    for p in sorted(vault.rglob(f"*{INCLUDED_EXT}")):
        if not p.is_file():
            continue
        rel = p.relative_to(vault)
        if _is_excluded(rel):
            continue
        targets.append(p)
    return targets


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def collect_obsidian(
    *,
    vault_path: Path | None = None,
    dst_root: Path | None = None,
    since_days: int | None = None,
) -> CollectStats:
    """Obsidian vault → L0 mirror (incremental).

    Args:
        vault_path: vault 루트 (기본: ``get_vault_path()``).
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/obsidian``).
        since_days: cutoff 일수. 지정 시 mtime 이 이 일수 안에 들지 *않는* 파일은
            scan 하되 mirror 안 함 (`files_skipped_by_cutoff` 로 카운트). 단 prev_state 에
            기록이 있으면 그대로 유지 — vault 안 절대 파일 손실 없음. ``--quick``
            (B1, eng-review 2026-05-13) 모드에서 사용.

    Returns:
        CollectStats — 처리 통계.
    """
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not vault.is_dir():
        stats.errors.append((vault, f"vault 없음: {vault}"))
        return stats

    # L0 루트 보호
    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    meta_path = dst / META_DIR / STATES_FILE
    prev_states = _load_states(meta_path)
    new_states: dict[str, FileState] = {}

    cutoff_ts: float | None = None
    if since_days is not None:
        if since_days < 0:
            raise ValueError(f"since_days must be >= 0, got {since_days}")
        cutoff_ts = time.time() - since_days * 86400.0

    for src in _enumerate_md(vault):
        stats.files_scanned += 1
        try:
            rel = src.relative_to(vault)
            rel_key = rel.as_posix()
            file_stat = src.stat()
            mtime = file_stat.st_mtime
            size = file_stat.st_size

            prev = prev_states.get(rel_key)

            # --quick cutoff: 일수 안에 들지 않는 파일은 skip — prev_state 보존.
            # 파일은 vault 에 그대로 남음, 단지 이번 mirror cycle 에서 비교 안 함.
            if cutoff_ts is not None and mtime < cutoff_ts:
                if prev is not None:
                    new_states[rel_key] = prev
                stats.files_skipped_by_cutoff += 1
                continue

            # Tier 1: mtime + size 일치 → 변경 없음 (가장 흔한 경로)
            if prev and prev.mtime == mtime and prev.size == size:
                new_states[rel_key] = prev
                stats.files_unchanged += 1
                continue

            # Tier 2: hash 비교 (mtime만 바뀐 케이스 — touch 등)
            sha = _file_sha256(src)
            if prev and prev.sha256 == sha:
                new_states[rel_key] = FileState(
                    rel_path=rel_key, mtime=mtime, size=size, sha256=sha
                )
                stats.files_unchanged += 1
                continue

            # Tier 3: 진짜 변경 또는 신규 — copy
            dst_file = dst / rel
            ensure_secure_dir(dst_file.parent)
            content = src.read_bytes()
            dst_file.write_bytes(content)
            with contextlib.suppress(OSError):
                os.chmod(dst_file, L0_FILE_MODE)

            stats.files_mirrored += 1
            stats.bytes_added += size
            new_states[rel_key] = FileState(
                rel_path=rel_key, mtime=mtime, size=size, sha256=sha
            )
        except OSError as exc:
            stats.errors.append((src, str(exc)))

    _save_states_atomic(meta_path, new_states)
    return stats
