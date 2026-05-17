"""Unit tests for synapse_memory.projects.registry (US1/US2)."""

from __future__ import annotations

import datetime
from pathlib import Path

from synapse_memory.projects.registry import (
    ProjectEntry,
    load_registry,
    mark_stale,
    save_registry,
    upsert_entry,
)


def test_load_empty_when_no_file(tmp_path: Path) -> None:
    registry = tmp_path / "projects.yaml"
    entries = load_registry(registry)
    assert entries == []


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    registry = tmp_path / "projects.yaml"
    entries = [
        ProjectEntry(
            path=Path("/proj/a"),
            target="both",
            registered_at=datetime.date(2026, 5, 17),
            last_sync=None,
            state="active",
        ),
        ProjectEntry(
            path=Path("/proj/b"),
            target="agents",
            registered_at=datetime.date(2026, 5, 16),
            last_sync=datetime.date(2026, 5, 17),
            state="active",
        ),
    ]
    save_registry(entries, registry)

    loaded = load_registry(registry)
    assert loaded == entries


def test_upsert_inserts_new_and_updates_existing(tmp_path: Path) -> None:
    entries: list[ProjectEntry] = []
    e1 = ProjectEntry(
        path=Path("/proj/a"),
        target="claude",
        registered_at=datetime.date(2026, 5, 17),
        last_sync=None,
    )
    e2 = ProjectEntry(
        path=Path("/proj/b"),
        target="both",
        registered_at=datetime.date(2026, 5, 17),
        last_sync=None,
    )
    e1_updated = ProjectEntry(
        path=Path("/proj/a"),
        target="both",
        registered_at=datetime.date(2026, 5, 17),
        last_sync=datetime.date(2026, 5, 18),
    )

    after_insert = upsert_entry(entries, e1)
    after_insert = upsert_entry(after_insert, e2)
    assert len(after_insert) == 2

    after_update = upsert_entry(after_insert, e1_updated)
    assert len(after_update) == 2
    target_a = [e for e in after_update if e.path == Path("/proj/a")][0]
    assert target_a.target == "both"
    assert target_a.last_sync == datetime.date(2026, 5, 18)


def test_mark_stale_updates_state(tmp_path: Path) -> None:
    entries = [
        ProjectEntry(
            path=Path("/proj/a"),
            target="both",
            registered_at=datetime.date(2026, 5, 17),
            last_sync=None,
            state="active",
        ),
        ProjectEntry(
            path=Path("/proj/b"),
            target="both",
            registered_at=datetime.date(2026, 5, 17),
            last_sync=None,
            state="active",
        ),
    ]
    after = mark_stale(entries, Path("/proj/a"))
    target_a = [e for e in after if e.path == Path("/proj/a")][0]
    target_b = [e for e in after if e.path == Path("/proj/b")][0]
    assert target_a.state == "stale"
    assert target_b.state == "active"
