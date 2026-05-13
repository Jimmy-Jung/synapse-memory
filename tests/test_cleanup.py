"""`synapse_memory.cleanup` — vault 청소 도우미 테스트.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

from synapse_memory.cleanup import (
    CleanupCandidate,
    CleanupKind,
    apply_cleanup,
    scan_cleanup_candidates,
    write_cleanup_manifest,
)
from synapse_memory.config import VaultFoldersConfig


def _set_mtime(path: Path, days_ago: int) -> None:
    """파일/폴더 mtime을 N일 전으로 조정."""
    target = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)).timestamp()
    os.utime(path, (target, target))


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for sub in (
        "00_Inbox",
        "10_Active",
        "20_Reference/Projects",
        "20_Reference/Companies",
        "30_Creative/Drafts",
        "40_Archive",
        "90_System/AI/MemoryInbox",
        "90_System/AI/DailyReports",
        "90_System/AI/recipes",
    ):
        (vault / sub).mkdir(parents=True)
    return vault


def test_scan_finds_stale_inbox_note(tmp_path):
    vault = _make_vault(tmp_path)
    fresh = vault / "00_Inbox" / "fresh.md"
    stale = vault / "00_Inbox" / "stale.md"
    fresh.write_text("recent", encoding="utf-8")
    stale.write_text("old", encoding="utf-8")
    _set_mtime(fresh, 5)
    _set_mtime(stale, 45)

    plan = scan_cleanup_candidates(vault)
    kinds = {c.kind for c in plan.candidates}
    assert CleanupKind.INBOX_STALE in kinds
    sources = [c.source_path for c in plan.candidates]
    assert str(stale) in sources
    assert str(fresh) not in sources


def test_scan_skips_pinned_inbox_note(tmp_path):
    vault = _make_vault(tmp_path)
    pinned = vault / "00_Inbox" / "pinned.md"
    pinned.write_text("---\npinned: true\n---\n\nbody", encoding="utf-8")
    _set_mtime(pinned, 60)

    plan = scan_cleanup_candidates(vault)
    assert not any(c.source_path == str(pinned) for c in plan.candidates)


def test_scan_skips_cleanup_marker_note(tmp_path):
    vault = _make_vault(tmp_path)
    marked = vault / "00_Inbox" / "marked.md"
    marked.write_text("---\ncleanup: skip\n---\n\nbody", encoding="utf-8")
    _set_mtime(marked, 60)

    plan = scan_cleanup_candidates(vault)
    assert not any(c.source_path == str(marked) for c in plan.candidates)


def test_scan_dormant_project(tmp_path):
    vault = _make_vault(tmp_path)
    project = vault / "10_Active" / "Acme" / "OldProj"
    project.mkdir(parents=True)
    note = project / "note.md"
    note.write_text("x", encoding="utf-8")
    _set_mtime(note, 120)
    _set_mtime(project, 120)

    plan = scan_cleanup_candidates(vault)
    assert any(
        c.kind == CleanupKind.DORMANT_PROJECT and c.source_path == str(project)
        for c in plan.candidates
    )


def test_scan_skips_dormant_when_pinned(tmp_path):
    vault = _make_vault(tmp_path)
    project = vault / "10_Active" / "Acme" / "Important"
    project.mkdir(parents=True)
    note = project / "note.md"
    note.write_text("---\npinned: true\n---\n\nbody", encoding="utf-8")
    _set_mtime(note, 120)

    plan = scan_cleanup_candidates(vault)
    assert not any(c.kind == CleanupKind.DORMANT_PROJECT for c in plan.candidates)


def test_scan_old_resume_draft(tmp_path):
    vault = _make_vault(tmp_path)
    resume = vault / "30_Creative" / "Drafts" / "Resume - Acme (2025-12).md"
    resume.write_text("draft", encoding="utf-8")
    _set_mtime(resume, 100)

    plan = scan_cleanup_candidates(vault)
    assert any(
        c.kind == CleanupKind.OLD_RESUME and c.source_path == str(resume) for c in plan.candidates
    )


def test_scan_stale_memory_inbox(tmp_path):
    vault = _make_vault(tmp_path)
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    old = inbox / "Profile-2025-12-01.md"
    new = inbox / "Profile-2026-05-13.md"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    _set_mtime(old, 90)
    _set_mtime(new, 1)

    plan = scan_cleanup_candidates(vault)
    sources = [c.source_path for c in plan.candidates]
    assert str(old) in sources
    assert str(new) not in sources


def test_scan_empty_card(tmp_path):
    vault = _make_vault(tmp_path)
    card = vault / "20_Reference" / "Projects" / "empty.md"
    card.write_text(
        "---\nproject_id: empty\ndisplay_name: Empty\nstatus: draft\n---\n\nbody",
        encoding="utf-8",
    )

    plan = scan_cleanup_candidates(vault)
    assert any(c.kind == CleanupKind.EMPTY_CARD for c in plan.candidates)


def test_scan_does_not_flag_active_card(tmp_path):
    vault = _make_vault(tmp_path)
    card = vault / "20_Reference" / "Projects" / "active.md"
    card.write_text(
        "---\nproject_id: a\ndisplay_name: A\nstatus: active\nkeywords:\n  - foo\n---\n",
        encoding="utf-8",
    )

    plan = scan_cleanup_candidates(vault)
    assert not any(c.kind == CleanupKind.EMPTY_CARD for c in plan.candidates)


def test_scan_empty_folder(tmp_path):
    vault = _make_vault(tmp_path)
    empty = vault / "10_Active" / "EmptyCompany"
    empty.mkdir()

    plan = scan_cleanup_candidates(vault)
    assert any(
        c.kind == CleanupKind.EMPTY_FOLDER and c.source_path == str(empty) for c in plan.candidates
    )


def test_apply_dry_run_does_not_move(tmp_path):
    vault = _make_vault(tmp_path)
    stale = vault / "00_Inbox" / "stale.md"
    stale.write_text("old", encoding="utf-8")
    _set_mtime(stale, 60)

    plan = scan_cleanup_candidates(vault)
    results = apply_cleanup(plan, dry_run=True, vault=vault)

    assert all(r.status == "dry_run" for r in results)
    assert stale.exists()


def test_apply_real_move_creates_archive_and_removes_source(tmp_path):
    vault = _make_vault(tmp_path)
    stale = vault / "00_Inbox" / "stale.md"
    stale.write_text("old", encoding="utf-8")
    _set_mtime(stale, 60)

    plan = scan_cleanup_candidates(vault)
    results = apply_cleanup(plan, dry_run=False, vault=vault)

    moved = [r for r in results if r.status == "moved"]
    assert len(moved) >= 1
    assert not stale.exists()
    archive_root = vault / "40_Archive"
    assert list(archive_root.rglob("stale.md"))


def test_cleanup_archive_root_uses_configured_folder(tmp_path):
    vault = _make_vault(tmp_path)
    folders = VaultFoldersConfig(archive="99_Archive")
    stale = vault / "00_Inbox" / "stale.md"
    stale.write_text("old", encoding="utf-8")
    _set_mtime(stale, 60)

    plan = scan_cleanup_candidates(vault, folders=folders)
    candidate = next(c for c in plan.candidates if c.source_path == str(stale))

    assert "99_Archive" in candidate.target_path
    assert "40_Archive" not in candidate.target_path

    results = apply_cleanup(plan, dry_run=False, vault=vault, folders=folders)

    assert any(r.status == "moved" for r in results)
    assert not stale.exists()
    assert list((vault / "99_Archive").rglob("stale.md"))
    assert not list((vault / "40_Archive").rglob("stale.md"))


def test_cleanup_manifest_uses_configured_reports_folder(tmp_path):
    vault = _make_vault(tmp_path)
    folders = VaultFoldersConfig()
    folders.system.ai.cleanup_reports = "99_Archive/CleanupReports"

    manifest = write_cleanup_manifest(
        vault,
        [],
        archive_date="2026-05-14",
        folders=folders,
    )

    assert manifest == vault / "99_Archive" / "CleanupReports" / "2026-05-14.md"
    assert manifest.exists()


def test_apply_empty_folder_removes_folder(tmp_path):
    vault = _make_vault(tmp_path)
    empty = vault / "10_Active" / "EmptyCo"
    empty.mkdir()

    plan = scan_cleanup_candidates(vault)
    results = apply_cleanup(plan, dry_run=False, vault=vault)

    statuses = [r.status for r in results]
    assert "moved" in statuses
    assert not empty.exists()


def test_apply_skips_protected_profile(tmp_path):
    """보호 경로(Profile.md)는 어떤 경우에도 이동되지 않음."""
    vault = _make_vault(tmp_path)
    profile = vault / "90_System" / "AI" / "Profile.md"
    profile.write_text("---\npinned: false\n---\n", encoding="utf-8")
    _set_mtime(profile, 120)

    plan = scan_cleanup_candidates(vault)
    # plan에 잘못 들어와도 apply가 막아야 함 — 임의로 후보를 강제 주입
    fake_cand = CleanupCandidate(
        kind=CleanupKind.INBOX_STALE,
        source_path=str(profile),
        target_path=str(vault / "40_Archive" / "x.md"),
        reason="강제 주입 (안전 테스트)",
    )
    results = apply_cleanup(plan, selected=[fake_cand], dry_run=False, vault=vault)
    assert any(r.status == "skipped" and "보호" in r.detail for r in results)
    assert profile.exists()


def test_write_manifest_includes_rollback_when_moved(tmp_path):
    vault = _make_vault(tmp_path)
    stale = vault / "00_Inbox" / "stale.md"
    stale.write_text("old", encoding="utf-8")
    _set_mtime(stale, 60)

    plan = scan_cleanup_candidates(vault)
    results = apply_cleanup(plan, dry_run=False, vault=vault)
    manifest = write_cleanup_manifest(vault, results)

    assert manifest.exists()
    body = manifest.read_text(encoding="utf-8")
    assert "Cleanup Report" in body
    assert "롤백 가이드" in body
    assert "이동된 항목" in body


def test_threshold_overrides(tmp_path):
    """임계값을 늘리면 후보가 빠짐."""
    vault = _make_vault(tmp_path)
    stale = vault / "00_Inbox" / "stale.md"
    stale.write_text("old", encoding="utf-8")
    _set_mtime(stale, 45)

    default_plan = scan_cleanup_candidates(vault)
    assert any(c.source_path == str(stale) for c in default_plan.candidates)

    relaxed_plan = scan_cleanup_candidates(vault, inbox_stale_days=180)
    assert not any(c.source_path == str(stale) for c in relaxed_plan.candidates)
