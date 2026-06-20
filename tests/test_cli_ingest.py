# tests/test_cli_ingest.py
"""ingest CLI 서브커맨드 — 인자 파싱 + 오케스트레이터 위임."""
from __future__ import annotations

from types import SimpleNamespace

import synapse_memory.cli as cli
from synapse_memory.wiki.ingest import IngestResult
from synapse_memory.wiki.ingest_audit import IngestAuditResult


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


def test_ingest_no_semantic_retrieval_flag(monkeypatch) -> None:
    captured = {}

    def fake_ingest(source, **kwargs):
        captured["semantic_retrieval"] = kwargs.get("semantic_retrieval")
        return IngestResult(source=source, docs_processed=0)

    monkeypatch.setattr(cli, "ingest_source", fake_ingest)
    rc = cli.main(["ingest", "--now", "--no-semantic-retrieval"])
    assert rc == 0
    assert captured["semantic_retrieval"] is False


def test_ingest_prints_skipped_count(monkeypatch, capsys) -> None:
    def fake_ingest(source, **kwargs):
        return IngestResult(source=source, docs_processed=1, docs_skipped=1)

    monkeypatch.setattr(cli, "ingest_source", fake_ingest)
    rc = cli.main(["ingest", "--now", "--source", "codex"])
    assert rc == 0
    assert "skipped=1" in capsys.readouterr().out


def test_ingest_audit_prints_queue_cost_summary(monkeypatch, capsys) -> None:
    captured = {}

    def fake_audit(source, **kwargs):
        captured["source"] = source
        captured["limit"] = kwargs.get("limit")
        return IngestAuditResult(
            source=source,
            docs_pending=4,
            docs_small=1,
            docs_sampled=2,
            docs_oversize=1,
            estimated_llm_calls=3,
            max_chars=150_000,
        )

    monkeypatch.setattr(cli, "audit_ingest_queue", fake_audit)
    rc = cli.main(["ingest-audit", "--source", "codex", "--limit", "5"])

    assert rc == 0
    assert captured == {"source": "codex", "limit": 5}
    out = capsys.readouterr().out
    assert "pending=4" in out
    assert "small=1" in out
    assert "sampled=2" in out
    assert "oversize=1" in out
    assert "estimated_llm_calls=3" in out


def test_ingest_audit_no_semantic_retrieval_flag(monkeypatch) -> None:
    captured = {}

    def fake_audit(source, **kwargs):
        captured["semantic_retrieval"] = kwargs.get("semantic_retrieval")
        return IngestAuditResult(source=source)

    monkeypatch.setattr(cli, "audit_ingest_queue", fake_audit)
    rc = cli.main(["ingest-audit", "--no-semantic-retrieval"])
    assert rc == 0
    assert captured["semantic_retrieval"] is False


def test_backfill_no_semantic_retrieval_flag(monkeypatch) -> None:
    captured = {}

    def fake_backfill(**kwargs):
        captured["semantic_retrieval"] = kwargs.get("semantic_retrieval")
        return SimpleNamespace(
            source=kwargs["source"],
            batches=0,
            docs_processed=0,
            pages_written=[],
            docs_skipped=0,
            errors=[],
        )

    monkeypatch.setattr(cli, "run_backfill", fake_backfill)
    rc = cli.main(["backfill", "--source", "codex", "--no-semantic-retrieval"])
    assert rc == 0
    assert captured["semantic_retrieval"] is False
