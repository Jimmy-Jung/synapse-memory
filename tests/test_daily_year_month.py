"""Integration tests for dated daily outputs and profile wiki writes."""

from __future__ import annotations

import datetime
from pathlib import Path

from synapse_memory.daily import DailyResult, write_daily_report
from synapse_memory.profile.extract import (
    ProfileFact,
    save_profile_update,
)


def _make_fact() -> ProfileFact:
    return ProfileFact(
        category="work_style",
        statement="기능 단위 커밋",
        confidence=0.9,
        extracted_at="2026-05-17",
    )


def test_save_profile_update_uses_profile_wiki_path(tmp_path: Path) -> None:
    path = save_profile_update(
        [_make_fact()],
        None,
        vault_path=tmp_path,
        date=datetime.date(2026, 5, 17),
    )
    expected = tmp_path / "Profile" / "user-profile.md"
    assert path == expected
    assert path.is_file()


def test_write_daily_report_uses_year_month_path(tmp_path: Path) -> None:
    result = DailyResult()
    path = write_daily_report(
        result,
        date=datetime.date(2026, 5, 17),
        vault_path=tmp_path,
    )
    expected = (
        tmp_path
        / "90_System"
        / "AI"
        / "DailyReports"
        / "2026"
        / "05"
        / "2026-05-17.md"
    )
    assert path == expected
    assert path.is_file()


def test_profile_second_run_appends_same_wiki_page(tmp_path: Path) -> None:
    save_profile_update(
        [_make_fact()],
        None,
        vault_path=tmp_path,
        date=datetime.date(2026, 5, 17),
    )
    save_profile_update(
        [_make_fact()],
        None,
        vault_path=tmp_path,
        date=datetime.date(2026, 5, 20),
    )
    path = tmp_path / "Profile" / "user-profile.md"
    content = path.read_text(encoding="utf-8")
    assert content.count("## Profile Facts") == 2


def test_month_boundary_creates_new_folder(tmp_path: Path) -> None:
    write_daily_report(
        DailyResult(),
        date=datetime.date(2026, 5, 31),
        vault_path=tmp_path,
    )
    write_daily_report(
        DailyResult(),
        date=datetime.date(2026, 6, 1),
        vault_path=tmp_path,
    )
    base = tmp_path / "90_System" / "AI" / "DailyReports"
    assert (base / "2026" / "05" / "2026-05-31.md").is_file()
    assert (base / "2026" / "06" / "2026-06-01.md").is_file()


def test_config_override_base_folder(tmp_path: Path) -> None:
    path = save_profile_update(
        [_make_fact()],
        None,
        vault_path=tmp_path,
        date=datetime.date(2026, 5, 17),
    )
    expected = tmp_path / "Profile" / "user-profile.md"
    assert path == expected
