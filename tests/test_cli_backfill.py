# tests/test_cli_backfill.py
import synapse_memory.cli as cli
from synapse_memory.wiki.backfill import BackfillResult


def test_cli_backfill(monkeypatch, capsys):
    captured = {}
    def fake(**kw):
        captured.update(kw)
        return BackfillResult(source="claude-code", batches=3, docs_processed=10, pages_written=["a"])
    monkeypatch.setattr(cli, "run_backfill", fake)
    rc = cli.main(["backfill", "--source", "claude-code", "--batch-size", "5"])
    assert rc == 0
    assert captured["batch_size"] == 5
    out = capsys.readouterr().out
    assert "10" in out and "3" in out


def test_cli_backfill_wait_lock_flag(monkeypatch):
    captured = {}

    def fake(**kw):
        captured.update(kw)
        return BackfillResult(source="codex", batches=0, docs_processed=0)

    monkeypatch.setattr(cli, "run_backfill", fake)
    rc = cli.main(["backfill", "--source", "codex", "--wait-lock"])

    assert rc == 0
    assert captured["wait_lock"] is True
