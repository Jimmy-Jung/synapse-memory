from __future__ import annotations

from synapse_memory.wiki.launchd import (
    LABEL,
    build_plist,
    install_watch,
    plist_path,
    uninstall_watch,
)


def test_build_plist_has_watchpaths_and_program() -> None:
    xml = build_plist(program_args=["synapse-memory", "watch", "run"],
                      watch_paths=["/home/u/.synapse/private/raw/claude-code"])
    assert "WatchPaths" in xml
    assert "watch" in xml and "run" in xml
    assert "/home/u/.synapse/private/raw/claude-code" in xml
    assert xml.lstrip().startswith("<?xml")


def test_plist_path_under_launchagents(tmp_path) -> None:
    assert plist_path(home=tmp_path) == tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def test_install_writes_plist_and_loads(tmp_path, monkeypatch) -> None:
    cmds = []
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: cmds.append(a))
    path = install_watch(home=tmp_path, program_args=["synapse-memory", "watch", "run"],
                         watch_paths=["/x/raw/claude-code"])
    assert path.is_file()
    assert cmds  # launchctl 호출됨


def test_uninstall_removes_plist(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: None)
    install_watch(home=tmp_path, program_args=["x"], watch_paths=["/y"])
    uninstall_watch(home=tmp_path)
    assert not plist_path(home=tmp_path).exists()
