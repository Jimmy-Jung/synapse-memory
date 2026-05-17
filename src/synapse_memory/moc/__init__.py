"""MOC (Map of Contents) generator for synapse-memory graph visualization."""

from __future__ import annotations

from pathlib import Path

from synapse_memory.config import get_config

__all__ = [
    "MOC_MARKER_START",
    "MOC_MARKER_END",
    "generate_moc_body",
    "write_or_update_moc",
]


MOC_MARKER_START = "<!-- SYNAPSE-MEMORY-MOC START -->"
MOC_MARKER_END = "<!-- SYNAPSE-MEMORY-MOC END -->"


def generate_moc_body(vault: Path) -> str:
    """vault 경로에 맞춘 dataview 인덱스 markdown body 생성."""
    cfg = get_config()
    folders = cfg.vault_folders

    projects_path = folders.reference.projects
    companies_path = folders.reference.companies
    memory_inbox_path = folders.system.ai.memory_inbox
    daily_reports_path = folders.system.ai.daily_reports

    parts: list[str] = [
        "## Map of Contents (auto-generated)",
        "",
        "> 이 페이지는 Dataview 플러그인이 필요합니다. 미설치 시 `synapse-memory doctor`로 안내를 확인하세요.",
        "",
        "### Projects (최신 10)",
        "",
        "```dataview",
        "TABLE status, role, period_start",
        f'FROM "{projects_path}"',
        "SORT file.mtime DESC",
        "LIMIT 10",
        "```",
        "",
        "### Companies",
        "",
        "```dataview",
        "LIST",
        f'FROM "{companies_path}"',
        "SORT file.mtime DESC",
        "LIMIT 10",
        "```",
        "",
        "### Profile updates (pending review)",
        "",
        "```dataview",
        "TABLE status, generated, fact_count, pattern_count",
        f'FROM "{memory_inbox_path}"',
        'WHERE type = "profile_update" AND status != "applied"',
        "SORT file.mtime DESC",
        "LIMIT 10",
        "```",
        "",
        "### Daily reports (최신 14)",
        "",
        "```dataview",
        "TABLE date, total_elapsed_s, errors_count, new_cards, new_facts",
        f'FROM "{daily_reports_path}"',
        "SORT file.mtime DESC",
        "LIMIT 14",
        "```",
        "",
        "### Node 색상 그룹 (Obsidian Graph 설정)",
        "",
        "Obsidian Graph view 설정에서 다음 그룹을 추가하면 노드 유형별 색상이 분리됩니다.",
        "",
        "- `tag:#node/card` — Card (Project / Company)",
        "- `tag:#node/profile-update` — Profile 후보",
        "- `tag:#node/daily-report` — DailyReport",
    ]
    return "\n".join(parts)


def write_or_update_moc(vault: Path) -> Path:
    """vault 90_System/AI/MOC.md를 생성·갱신. marker 외부 사용자 영역 보존."""
    cfg = get_config()
    ai_folder = cfg.vault_folders.system.ai
    moc_dir = vault / Path(ai_folder.profile).parent
    moc_dir.mkdir(parents=True, exist_ok=True)
    moc_path = moc_dir / "MOC.md"

    body = generate_moc_body(vault)
    wrapped = f"{MOC_MARKER_START}\n{body}\n{MOC_MARKER_END}\n"

    if not moc_path.is_file():
        moc_path.write_text(
            f"# Map of Contents\n\n{wrapped}",
            encoding="utf-8",
        )
        return moc_path

    text = moc_path.read_text(encoding="utf-8")
    start_idx = text.find(MOC_MARKER_START)
    end_idx = text.find(MOC_MARKER_END)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        new_text = text
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += "\n" + wrapped
        moc_path.write_text(new_text, encoding="utf-8")
        return moc_path

    suffix = text[end_idx + len(MOC_MARKER_END) :]
    inner = wrapped.rstrip("\n")
    if suffix.startswith("\n") or not suffix:
        new_text = text[:start_idx] + inner + suffix
    else:
        new_text = text[:start_idx] + inner + "\n" + suffix
    if new_text != text:
        moc_path.write_text(new_text, encoding="utf-8")
    return moc_path
