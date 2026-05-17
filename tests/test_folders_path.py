"""Unit tests for synapse_memory.folders path helpers (US1 + US2 공통 의존)."""

from __future__ import annotations

import datetime
from pathlib import Path

from synapse_memory.folders import find_candidate_files, year_month_path


def test_year_month_path_basic(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    result = year_month_path(base, datetime.date(2026, 5, 17))
    assert result == base / "2026" / "05"


def test_year_month_path_zero_pads_month(tmp_path: Path) -> None:
    base = tmp_path / "DailyReports"
    result = year_month_path(base, datetime.date(2026, 1, 9))
    assert result == base / "2026" / "01"
    assert "/1/" not in str(result)


def test_year_month_path_year_boundary(tmp_path: Path) -> None:
    base = tmp_path / "x"
    last_day = year_month_path(base, datetime.date(2026, 12, 31))
    next_day = year_month_path(base, datetime.date(2027, 1, 1))
    assert last_day != next_day
    assert last_day == base / "2026" / "12"
    assert next_day == base / "2027" / "01"


def test_year_month_path_does_not_create_directory(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    result = year_month_path(base, datetime.date(2026, 5, 17))
    assert not result.exists()


def test_find_candidate_files_recursive(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    nested = base / "2026" / "05"
    nested.mkdir(parents=True)
    target = nested / "Profile-2026-05-17.md"
    target.write_text("---\ntype: profile_update\n---\n")
    flat_legacy = base / "Profile-2026-04-23.md"
    flat_legacy.write_text("---\ntype: profile_update\n---\n")
    unrelated = nested / "notes.md"
    unrelated.write_text("hi")

    found = find_candidate_files(base, pattern="Profile-*.md")
    found_names = sorted(p.name for p in found)
    assert found_names == ["Profile-2026-04-23.md", "Profile-2026-05-17.md"]
