"""index.md — wiki 카탈로그 + 검토 큐 (마커 사이만 재생성, 사용자 편집 보존).

vault 루트 index.md의 MARKER_START/END 사이 블록만 lint가 갱신한다.
마커 밖 영역(사용자 메모)은 그대로 보존된다.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.wiki.page import VALID_TYPES, WikiPage

MARKER_START = "<!-- SYNAPSE:INDEX:START -->"
MARKER_END = "<!-- SYNAPSE:INDEX:END -->"

INDEX_FILENAME = "index.md"


def index_md_path(*, vault_path: Path | None = None) -> Path:
    """vault 루트의 index.md 경로."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / INDEX_FILENAME


def render_index(
    pages: list[WikiPage],
    *,
    orphans: list[str],
    review_items: list[dict],
) -> str:
    """마커 포함 인덱스 블록 생성 — 타입별 페이지 목록 + 고아 + 검토 큐."""
    lines: list[str] = [MARKER_START, "# Wiki Index", ""]

    by_type: dict[str, list[WikiPage]] = {t: [] for t in VALID_TYPES}
    for page in pages:
        by_type.setdefault(page.type, []).append(page)

    for page_type in VALID_TYPES:
        type_pages = sorted(by_type.get(page_type, []), key=lambda p: p.slug)
        if not type_pages:
            continue
        lines.append(f"## {page_type}")
        for page in type_pages:
            lines.append(f"- [[{page.slug}]] ({page.title})")
        lines.append("")

    lines.append("## 고아 페이지")
    if orphans:
        for slug in orphans:
            lines.append(f"- [[{slug}]]")
    else:
        lines.append("- (없음)")
    lines.append("")

    lines.append("## 검토 큐")
    if review_items:
        for item in review_items:
            kind = item.get("kind", "")
            slug = item.get("slug", "")
            other = item.get("other")
            if other:
                lines.append(f"- {kind}: [[{slug}]] ~ [[{other}]]")
            else:
                lines.append(f"- {kind}: [[{slug}]]")
    else:
        lines.append("- (없음)")
    lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def write_index(
    pages: list[WikiPage],
    *,
    orphans: list[str],
    review_items: list[dict],
    vault_path: Path | None = None,
) -> Path:
    """index.md 갱신 — 기존 파일이면 마커 사이만 교체, 없으면 새 생성."""
    path = index_md_path(vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    block = render_index(pages, orphans=orphans, review_items=review_items)

    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        start = existing.find(MARKER_START)
        end = existing.find(MARKER_END)
        if start != -1 and end != -1 and end > start:
            before = existing[:start]
            after = existing[end + len(MARKER_END):]
            path.write_text(before + block + after, encoding="utf-8")
            return path
        # 마커 없으면 기존 내용 뒤에 블록 추가
        sep = "" if existing.endswith("\n") or not existing else "\n"
        path.write_text(existing + sep + block + "\n", encoding="utf-8")
        return path

    path.write_text(block + "\n", encoding="utf-8")
    return path
