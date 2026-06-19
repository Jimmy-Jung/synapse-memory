# tests/test_wiki_backfill.py
from __future__ import annotations

import synapse_memory.wiki.backfill as bf
from synapse_memory.wiki.backfill import run_backfill
from synapse_memory.wiki.ingest import IngestResult


def test_backfill_loops_until_drained(tmp_path, monkeypatch) -> None:
    seq = [
        IngestResult(source="claude-code", docs_processed=2, pages_written=["a", "b"]),
        IngestResult(source="claude-code", docs_processed=2, pages_written=["c"]),
        IngestResult(source="claude-code", docs_processed=0),
    ]
    calls = {"n": 0}

    def fake_ingest(source, **kw):
        assert kw.get("checkpoint_each") is True
        assert kw.get("min_age_seconds") is None
        assert kw.get("limit") == 2
        r = seq[calls["n"]]
        calls["n"] += 1
        return r

    monkeypatch.setattr(bf, "ingest_source", fake_ingest)
    result = run_backfill(source="claude-code", vault_path=tmp_path, batch_size=2)
    assert result.batches == 3
    assert result.docs_processed == 4
    assert set(result.pages_written) == {"a", "b", "c"}


def test_backfill_respects_max_batches(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bf, "ingest_source",
        lambda source, **kw: IngestResult(source=source, docs_processed=kw["limit"], pages_written=["x"]))
    result = run_backfill(source="claude-code", vault_path=tmp_path, batch_size=5, max_batches=2)
    assert result.batches == 2


def test_backfill_breaks_on_all_failed_batch(tmp_path, monkeypatch) -> None:
    # 매 배치가 docs_processed>0 이지만 전부 errors → watermark 전진 없음 → stall break
    def fake_ingest(source, **kw):
        return IngestResult(source=source, docs_processed=kw["limit"],
                            pages_written=[], errors=["x"] * kw["limit"])
    monkeypatch.setattr(bf, "ingest_source", fake_ingest)
    result = run_backfill(source="claude-code", vault_path=tmp_path, batch_size=3)  # max_batches=None
    assert result.batches == 1  # 첫 배치 전부 실패 → 즉시 중단 (무한루프 아님)


def test_backfill_continues_after_skipped_batch(tmp_path, monkeypatch) -> None:
    seq = [
        IngestResult(source="codex", docs_processed=1, docs_skipped=1),
        IngestResult(source="codex", docs_processed=0),
    ]
    calls = {"n": 0}

    def fake_ingest(source, **kw):
        result = seq[calls["n"]]
        calls["n"] += 1
        return result

    monkeypatch.setattr(bf, "ingest_source", fake_ingest)
    result = run_backfill(source="codex", vault_path=tmp_path, batch_size=1)
    assert result.batches == 2
    assert result.docs_processed == 1
    assert result.docs_skipped == 1
