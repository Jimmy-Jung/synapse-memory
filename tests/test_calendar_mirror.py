"""Calendar mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.calendar.mirror import (
    META_DIR,
    STATES_FILE,
    collect_calendar,
)
from synapse_memory.storage.l0 import L0_DIR_MODE

_SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:abc-123
DTSTART:20260518T100000Z
DTEND:20260518T110000Z
SUMMARY:테스트 미팅
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture
def calendar_home(tmp_path: Path) -> Path:
    home = tmp_path / "Calendars"
    (home / "ABC-CAL.calendar" / "Events").mkdir(parents=True)
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "calendar"


class TestCollectCalendar:
    def test_mirrors_ics(
        self, calendar_home: Path, dst_root: Path
    ) -> None:
        ev = calendar_home / "ABC-CAL.calendar" / "Events" / "abc-123.ics"
        ev.write_text(_SAMPLE_ICS, encoding="utf-8")
        stats = collect_calendar(
            calendar_home=calendar_home, dst_root=dst_root
        )
        assert stats.files_scanned == 1
        assert stats.files_mirrored == 1
        dst_ev = (
            dst_root / "ABC-CAL.calendar" / "Events" / "abc-123.ics"
        )
        assert dst_ev.is_file()
        assert "테스트 미팅" in dst_ev.read_text(encoding="utf-8")

    def test_silent_when_uninstalled(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_calendar(
            calendar_home=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_idempotent(
        self, calendar_home: Path, dst_root: Path
    ) -> None:
        ev = calendar_home / "ABC-CAL.calendar" / "Events" / "abc.ics"
        ev.write_text(_SAMPLE_ICS, encoding="utf-8")
        collect_calendar(calendar_home=calendar_home, dst_root=dst_root)
        s2 = collect_calendar(
            calendar_home=calendar_home, dst_root=dst_root
        )
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, calendar_home: Path, dst_root: Path
    ) -> None:
        ev = calendar_home / "ABC-CAL.calendar" / "Events" / "abc.ics"
        ev.write_text(_SAMPLE_ICS, encoding="utf-8")
        collect_calendar(calendar_home=calendar_home, dst_root=dst_root)
        ev.write_text(_SAMPLE_ICS + "X-NOTE:changed\n", encoding="utf-8")
        s2 = collect_calendar(
            calendar_home=calendar_home, dst_root=dst_root
        )
        assert s2.files_mirrored == 1

    def test_l0_perms(
        self, calendar_home: Path, dst_root: Path
    ) -> None:
        ev = calendar_home / "ABC-CAL.calendar" / "Events" / "abc.ics"
        ev.write_text(_SAMPLE_ICS, encoding="utf-8")
        collect_calendar(calendar_home=calendar_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_calendar_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_calendar" in STEPS
        assert any(
            s.name == "collect_calendar"
            and s.description == "Calendar ICS mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_calendar(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_calendar" in actions
        assert callable(actions["collect_calendar"])
