"""Year/month folder path helpers for MemoryInbox and DailyReports."""

from __future__ import annotations

import datetime
from pathlib import Path

__all__ = ["year_month_path", "find_candidate_files"]


def year_month_path(base: Path, date: datetime.date) -> Path:
    return base / f"{date.year:04d}" / f"{date.month:02d}"


def find_candidate_files(base: Path, *, pattern: str = "Profile-*.md") -> list[Path]:
    if not base.exists():
        return []
    return sorted(base.rglob(pattern))
