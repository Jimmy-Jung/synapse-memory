import synapse_memory.cli as cli
from synapse_memory.wiki.daemon import CycleOutcome


def test_cli_watch_run(monkeypatch):
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=True, result=None))
    assert cli.main(["watch", "run"]) == 0


def test_cli_watch_run_skipped(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=False, skipped_reason="locked"))
    assert cli.main(["watch", "run"]) == 0
    assert "locked" in capsys.readouterr().out


def test_cli_watch_install(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "install_watch", lambda **kw: tmp_path / "x.plist")
    assert cli.main(["watch", "install"]) == 0
