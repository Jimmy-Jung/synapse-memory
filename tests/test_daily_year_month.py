"""Integration tests for US1: daily 실행 시 신규 파일이 {YYYY}/{MM}/ 하위에 생성되는지."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

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


def test_save_profile_update_uses_year_month_path(tmp_path: Path) -> None:
    path = save_profile_update(
        [_make_fact()],
        None,
        vault_path=tmp_path,
        date=datetime.date(2026, 5, 17),
    )
    expected = (
        tmp_path
        / "90_System"
        / "AI"
        / "MemoryInbox"
        / "2026"
        / "05"
        / "Profile-2026-05-17.md"
    )
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


def test_same_month_second_run_keeps_both_files(tmp_path: Path) -> None:
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
    month_dir = tmp_path / "90_System" / "AI" / "MemoryInbox" / "2026" / "05"
    files = sorted(p.name for p in month_dir.iterdir() if p.is_file())
    assert files == ["Profile-2026-05-17.md", "Profile-2026-05-20.md"]


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


def test_config_override_base_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synapse_memory.config import get_config

    cfg = get_config()
    monkeypatch.setattr(
        cfg.vault_folders.system.ai,
        "memory_inbox",
        "custom_inbox_dir",
        raising=False,
    )
    path = save_profile_update(
        [_make_fact()],
        None,
        vault_path=tmp_path,
        date=datetime.date(2026, 5, 17),
    )
    expected = (
        tmp_path
        / "custom_inbox_dir"
        / "2026"
        / "05"
        / "Profile-2026-05-17.md"
    )
    assert path == expected
