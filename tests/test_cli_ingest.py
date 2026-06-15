# tests/test_cli_ingest.py
"""ingest CLI 서브커맨드 — 인자 파싱 + 오케스트레이터 위임."""
from __future__ import annotations

import synapse_memory.cli as cli
from synapse_memory.wiki.ingest import IngestResult


def test_ingest_now_invokes_engine(monkeypatch, capsys) -> None:
    captured = {}

    def fake_ingest(source, **kwargs):
        captured["source"] = source
        captured["dry_run"] = kwargs.get("dry_run")
        return IngestResult(source=source, docs_processed=2, pages_written=["a", "b"])

    monkeypatch.setattr(cli, "ingest_source", fake_ingest)
    rc = cli.main(["ingest", "--now", "--source", "claude-code"])
    assert rc == 0
    assert captured["source"] == "claude-code"
    assert "2" in capsys.readouterr().out


def test_ingest_dry_run_flag(monkeypatch) -> None:
    captured = {}

    def fake_ingest(source, **kwargs):
        captured["dry_run"] = kwargs.get("dry_run")
        return IngestResult(source=source, docs_processed=0)

    monkeypatch.setattr(cli, "ingest_source", fake_ingest)
    cli.main(["ingest", "--now", "--dry-run"])
    assert captured["dry_run"] is True
