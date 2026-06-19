import synapse_memory.cli as cli
from synapse_memory.wiki.daemon import CycleOutcome
from synapse_memory.wiki.ingest import IngestResult


def test_cli_watch_run(monkeypatch, capsys):
    result = IngestResult(source="claude-code", docs_processed=2, pages_written=["x"])
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=True, result=result))
    assert cli.main(["watch", "run"]) == 0
    captured = capsys.readouterr()
    assert "watch run: docs=2, pages=1, errors=0" in captured.out
    assert "written: x" in captured.out
    assert captured.err == ""


def test_cli_watch_run_reports_errors(monkeypatch, capsys):
    result = IngestResult(
        source="claude-code",
        docs_processed=2,
        pages_written=[],
        errors=["doc-a: Claude Code CLI 미설치"],
    )
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=True, result=result))

    assert cli.main(["watch", "run"]) == 1
    captured = capsys.readouterr()
    assert "watch run: docs=2, pages=0, errors=1" in captured.out
    assert "error: doc-a: Claude Code CLI 미설치" in captured.err


def test_cli_watch_run_skipped(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=False, skipped_reason="locked"))
    assert cli.main(["watch", "run"]) == 0
    assert "locked" in capsys.readouterr().out


def test_cli_watch_install(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "install_watch", lambda **kw: tmp_path / "x.plist")
    assert cli.main(["watch", "install"]) == 0
