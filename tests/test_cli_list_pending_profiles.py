"""Integration tests for `synapse-memory list-pending-profiles` (014)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse_memory.cli import main


def _make_candidate(
    base: Path, year: int, month: int, day: int, *, applied: bool = False
) -> Path:
    sub = base / f"{year:04d}" / f"{month:02d}"
    sub.mkdir(parents=True, exist_ok=True)
    p = sub / f"Profile-{year:04d}-{month:02d}-{day:02d}.md"
    status = "applied" if applied else "pending_review"
    p.write_text(
        f"---\ntype: profile_update\ngenerated: {year:04d}-{month:02d}-{day:02d}\n"
        f"status: {status}\n---\n# 후보\n",
        encoding="utf-8",
    )
    return p


def _scaffold(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    inbox.mkdir(parents=True)
    return vault


def test_list_pending_recursive_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _scaffold(tmp_path)
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    _make_candidate(inbox, 2026, 5, 17)
    _make_candidate(inbox, 2026, 4, 23)

    rc = main(["list-pending-profiles", "--vault", str(vault)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "2026-05-17" in out
    assert "2026-04-23" in out


def test_list_pending_excludes_applied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _scaffold(tmp_path)
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    _make_candidate(inbox, 2026, 5, 17, applied=False)
    _make_candidate(inbox, 2026, 5, 13, applied=True)

    rc = main(["list-pending-profiles", "--vault", str(vault)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "2026-05-17" in out
    assert "2026-05-13" not in out


def test_list_pending_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _scaffold(tmp_path)
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    _make_candidate(inbox, 2026, 5, 17)

    rc = main(["list-pending-profiles", "--vault", str(vault), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["date"] == "2026-05-17"
    assert "Profile-2026-05-17.md" in payload[0]["path"]
    assert payload[0]["status"] == "pending_review"
