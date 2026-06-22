"""SessionStart hook tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse_memory.hooks import session_start


def _write_registry(home: Path, project: Path) -> None:
    home.mkdir(parents=True)
    (home / "projects.json").write_text(
        json.dumps(
            {
                "version": 1,
                "projects": [
                    {
                        "path": str(project),
                        "target": "claude",
                        "registered_at": "2026-06-11",
                        "last_sync": None,
                        "state": "active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_session_start_injects_context_for_registered_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    child = project / "subdir"
    child.mkdir(parents=True)
    _write_registry(home, project)
    rendered = home / "context" / "rendered.md"
    rendered.parent.mkdir()
    rendered.write_text("Second Brain context", encoding="utf-8")
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.chdir(child)

    rc = session_start.main()

    assert rc == 0
    assert capsys.readouterr().out == "Second Brain context"


def test_session_start_is_silent_for_unregistered_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / ".synapse"
    registered = tmp_path / "registered"
    other = tmp_path / "other"
    other.mkdir()
    _write_registry(home, registered)
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.chdir(other)

    rc = session_start.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_session_start_suggests_registration_once_for_unregistered_git_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.setenv("SYNAPSE_HOOK_SUGGEST_REGISTER", "1")
    monkeypatch.chdir(project)

    first_rc = session_start.main()
    first_out = capsys.readouterr().out
    second_rc = session_start.main()
    second_out = capsys.readouterr().out

    assert first_rc == 0
    assert second_rc == 0
    assert "미등록" in first_out
    assert "synapse-memory setup" in first_out
    assert "--no-marker" not in first_out
    assert second_out == ""


def test_session_start_suggests_registration_from_settings_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    settings = home / "context" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "version": 1,
                "hook": {
                    "enabled": True,
                    "suggest_register": True,
                    "max_inject_bytes": 2048,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.chdir(project)

    rc = session_start.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "synapse-memory setup" in out
    assert "--no-marker" not in out


def test_session_start_respects_settings_max_inject_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    project.mkdir()
    _write_registry(home, project)
    rendered = home / "context" / "rendered.md"
    rendered.parent.mkdir()
    rendered.write_text("abcdef", encoding="utf-8")
    (home / "context" / "settings.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hook": {
                    "enabled": True,
                    "suggest_register": False,
                    "max_inject_bytes": 3,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.chdir(project)

    rc = session_start.main()

    assert rc == 0
    assert capsys.readouterr().out == "abc"


def test_session_start_fallback_when_cache_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / ".synapse"
    project = tmp_path / "project"
    project.mkdir()
    _write_registry(home, project)
    monkeypatch.setenv("SYNAPSE_HOME", str(home))
    monkeypatch.chdir(project)

    rc = session_start.main()

    assert rc == 0
    assert "컨텍스트 캐시 없음" in capsys.readouterr().out
