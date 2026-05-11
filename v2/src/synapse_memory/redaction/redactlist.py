"""Redact-list — allowlist의 반대.

사용자가 NDA/비공개로 지정한 회사·프로젝트·키워드를 모든 raw에서 무조건 mask.
Pass 1 단계에 동적 패턴으로 합류 (priority=200 — 가장 높음).

위치: ``~/.synapse/private/.redactlist``
형식: 한 줄 = 한 항목, ``#`` 주석, 빈 줄 무시. case-insensitive 매칭.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import re
from pathlib import Path

from synapse_memory.redaction.patterns import Pattern
from synapse_memory.storage.l0 import l0_root

REDACTLIST_PRIORITY = 200  # 모든 카테고리보다 먼저 매치
REDACTLIST_NAME = "redactlist"
REDACTLIST_PLACEHOLDER = "REDACT"


def _redactlist_path() -> Path:
    return l0_root() / ".redactlist"


def load_redactlist(path: Path | None = None) -> list[str]:
    """파일에서 redact 항목 로드. 입력 순서 보존 (사용자 의도 우선)."""
    p = (path or _redactlist_path()).expanduser()
    if not p.exists():
        return []
    items: list[str] = []
    seen: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s in seen:
            continue
        seen.add(s)
        items.append(s)
    return items


def build_redactlist_patterns(items: list[str]) -> list[Pattern]:
    """각 redact 항목 → Pattern. case-insensitive 정확 substring 매치.

    긴 항목부터 매치되도록 정렬 (e.g. "ProjectXYZ"가 "Project"보다 우선).
    """
    if not items:
        return []
    patterns: list[Pattern] = []
    sorted_items = sorted(set(items), key=len, reverse=True)
    for item in sorted_items:
        if not item.strip():
            continue
        patterns.append(
            Pattern(
                name=REDACTLIST_NAME,
                regex=re.compile(re.escape(item), re.IGNORECASE),
                placeholder_prefix=REDACTLIST_PLACEHOLDER,
                priority=REDACTLIST_PRIORITY,
            )
        )
    return patterns


def write_redactlist(items: list[str], path: Path | None = None) -> Path:
    """리스트를 파일로 저장 (CLI add/remove용). 헤더 주석 포함."""
    p = (path or _redactlist_path()).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# synapse-memory redact-list\n"
        "# 한 줄 = 한 항목. 모든 raw 데이터에서 [REDACT_*]로 마스킹됨.\n"
        "# case-insensitive 매칭.\n"
        "\n"
    )
    body = "\n".join(items) + "\n" if items else ""
    p.write_text(header + body, encoding="utf-8")
    return p


def add_redactlist_item(item: str, path: Path | None = None) -> bool:
    """항목 추가. 이미 있으면 False, 새로 추가했으면 True."""
    item = item.strip()
    if not item:
        raise ValueError("빈 항목 추가 불가")
    items = load_redactlist(path)
    if item in items:
        return False
    items.append(item)
    write_redactlist(items, path)
    return True


def remove_redactlist_item(item: str, path: Path | None = None) -> bool:
    """항목 제거. 있었으면 True, 없었으면 False."""
    items = load_redactlist(path)
    if item not in items:
        return False
    items.remove(item)
    write_redactlist(items, path)
    return True
