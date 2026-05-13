"""Claude Code 로그 mirror — incremental tail.

소스 ``~/.claude/projects/<slug>/<sessionId>.jsonl``를 ``~/.synapse/private/raw/
claude-code/projects/<slug>/<sessionId>.jsonl``로 복제. 매 호출마다 새 줄만 append.

핵심 보장
--------
- **Partial-line safe**: Claude Code가 동시에 쓰고 있을 수 있어 마지막 ``\\n``까지만 처리.
- **Idempotent**: 같은 호출 두 번 = 첫 호출 + 빈 두 번째.
- **Rotation safe**: src 크기가 마지막 offset보다 작아지면 처음부터 다시 mirror.
- **Atomic offset 갱신**: write → fsync → rename. 중간에 죽어도 일관성 유지.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
SUBPATH = Path("raw") / "claude-code"
OFFSETS_DIR = ".offsets"


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------


@dataclass
class FileMirrorResult:
    src: Path
    dst: Path
    bytes_added: int
    truncated_reset: bool = False  # rotation 감지 시 True


@dataclass
class CollectStats:
    files_scanned: int = 0
    files_mirrored: int = 0  # 변경분 있던 파일 수
    bytes_added: int = 0
    truncations: int = 0
    skipped_empty: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned={self.files_scanned} mirrored={self.files_mirrored} "
            f"bytes+={self.bytes_added} truncations={self.truncations} "
            f"skipped_empty={self.skipped_empty} errors={len(self.errors)}"
        )


# ---------------------------------------------------------------------------
# 단일 파일 mirror
# ---------------------------------------------------------------------------


def _read_offset(offset_path: Path) -> int:
    """offset 파일에서 마지막 처리된 byte 수 읽기. 없으면 0."""
    if not offset_path.exists():
        return 0
    try:
        return int(offset_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0


def _write_offset_atomic(offset_path: Path, value: int) -> None:
    """offset을 atomic하게 갱신 (write to tmp → fsync → rename)."""
    ensure_secure_dir(offset_path.parent)
    tmp = offset_path.with_suffix(offset_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(value))
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(tmp, L0_FILE_MODE)
    os.replace(tmp, offset_path)


def _last_newline_pos(buf: bytes) -> int:
    """buf에서 마지막 ``\\n``의 위치 + 1 반환. 없으면 0.

    완전한 줄까지의 byte 길이로 사용. partial line은 다음 호출로 미룸.
    """
    idx = buf.rfind(b"\n")
    return idx + 1 if idx >= 0 else 0


def mirror_jsonl(
    src: Path,
    dst: Path,
    offset_path: Path,
) -> FileMirrorResult:
    """src의 새 줄을 dst에 append. offset_path에 진행상황 보존.

    파일이 binary로 다뤄짐 (UTF-8 BOM/한글 이슈 회피). JSONL 가정이지만 파싱 안 함.

    Args:
        src: 원본 jsonl (예: ``~/.claude/projects/.../<id>.jsonl``).
        dst: L0 사본 경로.
        offset_path: src의 마지막 처리 byte 수 보존 위치.

    Returns:
        FileMirrorResult — 추가된 byte 수, rotation 감지 여부.
    """
    if not src.exists():
        return FileMirrorResult(src=src, dst=dst, bytes_added=0)

    src_size = src.stat().st_size
    last_offset = _read_offset(offset_path)

    # rotation 감지: src가 마지막 offset보다 작아짐 → 처음부터 다시
    truncated = False
    if src_size < last_offset:
        truncated = True
        last_offset = 0
        # dst도 리셋
        if dst.exists():
            dst.unlink()

    if src_size == last_offset:
        return FileMirrorResult(src=src, dst=dst, bytes_added=0, truncated_reset=truncated)

    # src 읽기 (새 부분만)
    with open(src, "rb") as f:
        f.seek(last_offset)
        new_data = f.read(src_size - last_offset)

    # partial line 컷
    safe_len = _last_newline_pos(new_data)
    if safe_len == 0:
        # 완전한 줄이 하나도 없음 — 다음 호출까지 보류
        return FileMirrorResult(src=src, dst=dst, bytes_added=0, truncated_reset=truncated)

    safe_data = new_data[:safe_len]

    # dst 부모 디렉토리 보장
    ensure_secure_dir(dst.parent)

    # append (binary)
    with open(dst, "ab") as f:
        f.write(safe_data)
        f.flush()
        os.fsync(f.fileno())

    # 파일 권한 (최초 생성 시)
    with contextlib.suppress(OSError):
        os.chmod(dst, L0_FILE_MODE)

    # offset 갱신 (atomic)
    new_offset = last_offset + safe_len
    _write_offset_atomic(offset_path, new_offset)

    return FileMirrorResult(
        src=src,
        dst=dst,
        bytes_added=safe_len,
        truncated_reset=truncated,
    )


# ---------------------------------------------------------------------------
# 전체 수집
# ---------------------------------------------------------------------------


def _enumerate_jsonl(claude_home: Path) -> list[Path]:
    """수집 대상 jsonl 파일 목록.

    포함:
        ~/.claude/projects/<slug>/<id>.jsonl
        ~/.claude/history.jsonl

    제외 (현 단계):
        ~/.claude/sessions/*.json (세션 메타만, 가치 낮음)
        ~/.claude/projects/<slug>/<id>/ (하위 디렉토리, W2에서 평가)
        cache, telemetry, mcp-needs-auth-cache.json (보안/노이즈)
    """
    targets: list[Path] = []

    history = claude_home / "history.jsonl"
    if history.is_file():
        targets.append(history)

    projects = claude_home / "projects"
    if projects.is_dir():
        for proj_dir in sorted(projects.iterdir()):
            if not proj_dir.is_dir():
                continue
            for f in sorted(proj_dir.iterdir()):
                if f.is_file() and f.suffix == ".jsonl":
                    targets.append(f)

    return targets


def _dst_for(src: Path, claude_home: Path, dst_root: Path) -> Path:
    """src 위치를 dst_root 아래 거울 경로로 변환."""
    rel = src.relative_to(claude_home)
    return dst_root / rel


def _offset_path_for(src: Path, claude_home: Path, dst_root: Path) -> Path:
    """offset 메타 파일 경로. ``<dst_root>/.offsets/<rel-with-__>.offset``."""
    rel = src.relative_to(claude_home)
    flat = str(rel).replace(os.sep, "__").replace("/", "__")
    return dst_root / OFFSETS_DIR / f"{flat}.offset"


def collect_claude_code(
    *,
    claude_home: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Claude Code 데이터 1회 수집 (incremental).

    Args:
        claude_home: ~/.claude (기본). 테스트에서 override.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/claude-code``).

    Returns:
        CollectStats — 처리 통계.
    """
    claude_home = (claude_home or DEFAULT_CLAUDE_HOME).expanduser().resolve()
    dst_root = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    if not claude_home.is_dir():
        stats.errors.append((claude_home, f"Claude home 없음: {claude_home}"))
        return stats

    # dst_root가 L0 루트의 후손이면 루트 자체도 0700으로 보호 (이전 도구가 0755로
    # 만들어놨을 수 있음)
    if dst_root.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()

    ensure_secure_dir(dst_root)
    ensure_secure_dir(dst_root / OFFSETS_DIR)

    for src in _enumerate_jsonl(claude_home):
        stats.files_scanned += 1
        try:
            if src.stat().st_size == 0:
                stats.skipped_empty += 1
                continue
            dst = _dst_for(src, claude_home, dst_root)
            offset = _offset_path_for(src, claude_home, dst_root)
            result = mirror_jsonl(src, dst, offset)
            if result.truncated_reset:
                stats.truncations += 1
            if result.bytes_added > 0:
                stats.files_mirrored += 1
                stats.bytes_added += result.bytes_added
        except OSError as exc:
            stats.errors.append((src, str(exc)))

    return stats
