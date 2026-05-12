"""Raw source chunking for RAG indexing.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from synapse_memory.storage.l0 import l0_root

RawSourceKind = Literal["raw_obsidian", "raw_claude_code"]

DEFAULT_CHUNK_TOKENS = 512
DEFAULT_CHUNK_OVERLAP = 64
CLAUDE_SOURCE_EXTENSIONS = frozenset({".jsonl", ".json", ".md", ".txt"})
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*|[가-힣]+")


@dataclass(frozen=True)
class RawSource:
    source_kind: RawSourceKind
    path: Path
    root_path: Path


@dataclass(frozen=True)
class RawChunk:
    id: str
    source_kind: RawSourceKind
    path: str
    chunk_index: int
    text: str
    created: str
    display_name: str


def tokenize_text(text: str) -> list[str]:
    """텍스트를 chunk 단위 계산용 token으로 분리한다."""
    return [match.group(0) for match in _TOKEN_PATTERN.finditer(text)]


def chunk_text(
    text: str,
    *,
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Raw text를 deterministic token window로 나눈다."""
    if max_tokens < 1:
        raise ValueError("max_tokens must be >= 1")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")

    token_matches = list(_TOKEN_PATTERN.finditer(text))
    if not token_matches:
        return []
    if len(token_matches) <= max_tokens:
        return [_slice_text(text, token_matches, 0, len(token_matches))]

    chunks: list[str] = []
    step = max_tokens - overlap
    start = 0
    while start < len(token_matches):
        end = min(start + max_tokens, len(token_matches))
        chunks.append(_slice_text(text, token_matches, start, end))
        if end == len(token_matches):
            break
        start += step
    return chunks


def discover_raw_sources(
    *,
    vault_path: Path | None = None,
    l0_path: Path | None = None,
) -> list[RawSource]:
    """Obsidian active notes and redacted Claude Code files를 찾는다."""
    sources: list[RawSource] = []

    if vault_path is not None:
        vault_root = vault_path.expanduser().resolve()
        active_root = vault_root / "10_Active"
        if active_root.is_dir():
            sources.extend(
                RawSource("raw_obsidian", path, vault_root)
                for path in sorted(active_root.rglob("*.md"))
                if path.is_file()
            )

    l0_resolved = (l0_path or l0_root()).expanduser().resolve()
    claude_root = l0_resolved / "redacted" / "claude-code"
    if claude_root.is_dir():
        sources.extend(
            RawSource("raw_claude_code", path, l0_resolved)
            for path in sorted(claude_root.rglob("*"))
            if path.is_file() and path.suffix.lower() in CLAUDE_SOURCE_EXTENSIONS
        )

    return sources


def raw_chunks_from_file(
    path: Path,
    *,
    source_kind: RawSourceKind,
    root_path: Path,
    redact: Callable[[str], str],
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[RawChunk]:
    """파일 하나를 읽어 redacted raw chunks로 변환한다."""
    source_path = path.expanduser().resolve()
    raw_text = source_path.read_text(encoding="utf-8")
    effective_overlap = min(overlap, max_tokens - 1)
    raw_chunks = chunk_text(
        raw_text,
        max_tokens=max_tokens,
        overlap=effective_overlap,
    )
    if not raw_chunks:
        return []

    relative_path = _relative_display_path(source_path, root_path)
    created = _mtime_iso(source_path)
    chunks: list[RawChunk] = []
    for index, chunk in enumerate(raw_chunks):
        redacted = redact(chunk).strip()
        if not redacted:
            continue
        chunks.append(
            RawChunk(
                id=_raw_chunk_id(source_kind, relative_path, index),
                source_kind=source_kind,
                path=relative_path,
                chunk_index=index,
                text=redacted,
                created=created,
                display_name=source_path.name,
            )
        )
    return chunks


def _relative_display_path(path: Path, root_path: Path) -> str:
    root = root_path.expanduser().resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _raw_chunk_id(source_kind: RawSourceKind, relative_path: str, chunk_index: int) -> str:
    digest = hashlib.sha1(f"{source_kind}:{relative_path}".encode()).hexdigest()[:12]
    return f"{source_kind}:{digest}:{chunk_index}"


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _slice_text(text: str, token_matches: list[re.Match[str]], start: int, end: int) -> str:
    first = token_matches[start].start()
    last = token_matches[end - 1].end()
    return " ".join(text[first:last].split())
