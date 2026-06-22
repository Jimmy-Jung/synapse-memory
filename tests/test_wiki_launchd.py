from __future__ import annotations

import plistlib
import subprocess

import pytest

from synapse_memory.wiki.launchd import (
    LABEL,
    LaunchctlError,
    _launchctl,
    build_plist,
    install_watch,
    plist_path,
    uninstall_watch,
)


def test_build_plist_has_startinterval_and_program() -> None:
    # 020: WatchPaths → StartInterval(주기 실행). self-trigger 제거.
    xml = build_plist(program_args=["synapse-memory", "watch", "run"],
                      interval_seconds=1200)
    assert "StartInterval" in xml
    assert "ThrottleInterval" in xml
    assert "WatchPaths" not in xml
    assert "watch" in xml and "run" in xml
    assert "1200" in xml
    assert xml.lstrip().startswith("<?xml")


def test_build_plist_includes_daemon_path(monkeypatch) -> None:
    monkeypatch.setenv(
        "HOME",
        "/Users/jimmy",
    )
    monkeypatch.setenv("PATH", "/Users/jimmy/.codex/tmp/arg0:/Users/jimmy/bin:/usr/bin")
    monkeypatch.setattr(
        "synapse_memory.wiki.launchd.shutil.which",
        lambda name: "/Users/jimmy/.local/bin/claude" if name == "claude" else None,
    )

    xml = build_plist(
        program_args=["/opt/synapse/bin/synapse-memory", "watch", "run"],
        interval_seconds=1200,
    )
    payload = plistlib.loads(xml.encode("utf-8"))

    path = payload["EnvironmentVariables"]["PATH"]
    assert path.split(":")[:3] == [
        "/opt/synapse/bin",
        "/Users/jimmy/.local/bin",
        "/Users/jimmy/bin",
    ]
    assert "/usr/bin" in path
    assert "/bin" in path
    assert "/Users/jimmy/.codex/tmp/arg0" not in path


def test_build_plist_includes_codex_dir(monkeypatch) -> None:
    """engine=codex가 nvm 등 비표준 경로일 때 데몬 PATH에 포함돼야 한다(회귀)."""
    monkeypatch.setenv("HOME", "/Users/jimmy")
    monkeypatch.setenv("PATH", "/usr/bin")
    resolved = {
        "claude": "/Users/jimmy/.local/bin/claude",
        "codex": "/Users/jimmy/.nvm/versions/node/v22.18.0/bin/codex",
    }
    monkeypatch.setattr(
        "synapse_memory.wiki.launchd.shutil.which",
        lambda name: resolved.get(name),
    )

    xml = build_plist(
        program_args=["/opt/synapse/bin/synapse-memory", "watch", "run"],
        interval_seconds=3600,
    )
    path = plistlib.loads(xml.encode("utf-8"))["EnvironmentVariables"]["PATH"]
    assert "/Users/jimmy/.nvm/versions/node/v22.18.0/bin" in path.split(":")


def test_plist_path_under_launchagents(tmp_path) -> None:
    assert plist_path(home=tmp_path) == tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def test_install_writes_plist_and_loads(tmp_path, monkeypatch) -> None:
    cmds = []
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: cmds.append(a))
    path = install_watch(home=tmp_path, program_args=["synapse-memory", "watch", "run"],
                         interval_seconds=1200)
    assert path.is_file()
    assert cmds  # launchctl 호출됨


def test_launchctl_raises_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "synapse_memory.wiki.launchd.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=5,
            stderr=b"not allowed",
        ),
    )

    with pytest.raises(LaunchctlError, match="not allowed"):
        _launchctl("load", "-w", "/tmp/x.plist")


def test_uninstall_removes_plist(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: None)
    install_watch(home=tmp_path, program_args=["x"], interval_seconds=1200)
    uninstall_watch(home=tmp_path)
    assert not plist_path(home=tmp_path).exists()
