from __future__ import annotations

from synapse_memory.wiki.launchd import (
    LABEL,
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


def test_plist_path_under_launchagents(tmp_path) -> None:
    assert plist_path(home=tmp_path) == tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def test_install_writes_plist_and_loads(tmp_path, monkeypatch) -> None:
    cmds = []
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: cmds.append(a))
    path = install_watch(home=tmp_path, program_args=["synapse-memory", "watch", "run"],
                         interval_seconds=1200)
    assert path.is_file()
    assert cmds  # launchctl 호출됨


def test_uninstall_removes_plist(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: None)
    install_watch(home=tmp_path, program_args=["x"], interval_seconds=1200)
    uninstall_watch(home=tmp_path)
    assert not plist_path(home=tmp_path).exists()
