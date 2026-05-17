"""Unit tests for US2: flat → year/month migration (scan + execute)."""

from __future__ import annotations

import datetime
from pathlib import Path

from synapse_memory.folders.migrate import (
    PROFILE_PATTERN,
    MigrationPlan,
    execute_migration,
    scan_flat_files,
)


def _make_flat(base: Path, name: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    p = base / name
    p.write_text("---\ntype: profile_update\n---\n")
    return p


def test_scan_flat_files_returns_plans(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    _make_flat(base, "Profile-2026-04-23.md")
    _make_flat(base, "Profile-2026-05-17.md")

    plans, skipped = scan_flat_files(base, PROFILE_PATTERN)
    plan_dates = sorted(p.date for p in plans)
    assert plan_dates == [
        datetime.date(2026, 4, 23),
        datetime.date(2026, 5, 17),
    ]
    assert skipped == []


def test_scan_skips_unknown_pattern(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    _make_flat(base, "Profile-2026-05-17.md")
    _make_flat(base, "Profile-draft.md")
    _make_flat(base, "notes.md")

    plans, skipped = scan_flat_files(base, PROFILE_PATTERN)
    assert len(plans) == 1
    skipped_names = sorted(p.name for p in skipped)
    assert skipped_names == ["Profile-draft.md", "notes.md"]


def test_scan_ignores_already_migrated_files(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    nested = base / "2026" / "05"
    nested.mkdir(parents=True)
    (nested / "Profile-2026-05-17.md").write_text("ok")

    plans, _ = scan_flat_files(base, PROFILE_PATTERN)
    assert plans == []


def test_execute_dry_run_does_not_mutate(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    src = _make_flat(base, "Profile-2026-05-17.md")
    plans, _ = scan_flat_files(base, PROFILE_PATTERN)

    result = execute_migration(plans, dry_run=True)

    assert len(result.moved) == 1
    assert src.exists()
    expected_dst = base / "2026" / "05" / "Profile-2026-05-17.md"
    assert not expected_dst.exists()


def test_execute_real_moves_files(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    src = _make_flat(base, "Profile-2026-05-17.md")
    plans, _ = scan_flat_files(base, PROFILE_PATTERN)

    result = execute_migration(plans, dry_run=False)

    assert len(result.moved) == 1
    assert not src.exists()
    expected_dst = base / "2026" / "05" / "Profile-2026-05-17.md"
    assert expected_dst.is_file()


def test_execute_detects_collision(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    flat = _make_flat(base, "Profile-2026-05-17.md")
    nested = base / "2026" / "05"
    nested.mkdir(parents=True)
    existing = nested / "Profile-2026-05-17.md"
    existing.write_text("already there")

    plan = MigrationPlan(
        src=flat,
        dst=existing,
        date=datetime.date(2026, 5, 17),
    )
    result = execute_migration([plan], dry_run=False)

    assert result.moved == []
    assert len(result.conflicts) == 1
    assert flat.exists(), "충돌 시 원본 보존"
    assert existing.read_text() == "already there", "기존 파일 덮어쓰기 금지"


def test_execute_idempotent_after_success(tmp_path: Path) -> None:
    base = tmp_path / "MemoryInbox"
    _make_flat(base, "Profile-2026-05-17.md")
    plans, _ = scan_flat_files(base, PROFILE_PATTERN)
    execute_migration(plans, dry_run=False)

    plans_2nd, _ = scan_flat_files(base, PROFILE_PATTERN)
    assert plans_2nd == []
