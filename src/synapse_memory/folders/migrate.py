"""Flat → year/month migration for MemoryInbox / DailyReports."""

from __future__ import annotations

import datetime
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.folders import year_month_path

__all__ = [
    "DAILY_REPORT_PATTERN",
    "PROFILE_PATTERN",
    "MigrationPlan",
    "MigrationResult",
    "execute_migration",
    "scan_flat_files",
]


PROFILE_PATTERN = re.compile(r"^Profile-(\d{4})-(\d{2})-(\d{2})\.md$")
DAILY_REPORT_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")


@dataclass(frozen=True)
class MigrationPlan:
    src: Path
    dst: Path
    date: datetime.date


@dataclass
class MigrationResult:
    moved: list[MigrationPlan] = field(default_factory=list)
    skipped_unknown: list[Path] = field(default_factory=list)
    conflicts: list[tuple[Path, Path]] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)


def scan_flat_files(
    folder: Path, pattern: re.Pattern[str]
) -> tuple[list[MigrationPlan], list[Path]]:
    if not folder.is_dir():
        return [], []
    plans: list[MigrationPlan] = []
    skipped: list[Path] = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file():
            continue
        match = pattern.match(entry.name)
        if match is None:
            skipped.append(entry)
            continue
        year, month, day = (int(g) for g in match.groups())
        date = datetime.date(year, month, day)
        dst_dir = year_month_path(folder, date)
        dst = dst_dir / entry.name
        plans.append(MigrationPlan(src=entry, dst=dst, date=date))
    return plans, skipped


def execute_migration(
    plans: list[MigrationPlan], *, dry_run: bool = False
) -> MigrationResult:
    result = MigrationResult()
    for plan in plans:
        if plan.dst.exists():
            result.conflicts.append((plan.src, plan.dst))
            continue
        if dry_run:
            result.moved.append(plan)
            continue
        try:
            plan.dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(plan.src), str(plan.dst))
        except OSError as exc:
            result.errors.append((plan.src, str(exc)))
            continue
        result.moved.append(plan)
    return result
