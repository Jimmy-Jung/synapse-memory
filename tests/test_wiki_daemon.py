from __future__ import annotations

import synapse_memory.wiki.daemon as d
from synapse_memory.wiki.ingest import IngestResult


def test_cycle_runs_ingest_with_idle_filter(tmp_path, monkeypatch) -> None:
    calls = {}
    def fake_ingest(source, **kw):
        calls["source"] = source
        calls["min_age_seconds"] = kw.get("min_age_seconds")
        return IngestResult(source=source, docs_processed=1, pages_written=["x"])
    monkeypatch.setattr(d, "ingest_source", fake_ingest)
    outcome = d.run_watch_cycle(source="claude-code", lock_path=tmp_path / "l.lock", idle_minutes=3)
    assert outcome.ran is True
    assert calls["source"] == "claude-code"
    assert calls["min_age_seconds"] == 180


def test_cycle_skips_when_locked(tmp_path, monkeypatch) -> None:
    from synapse_memory.wiki.lock import FileLock
    p = tmp_path / "l.lock"
    monkeypatch.setattr(d, "ingest_source",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출되면 안 됨")))
    with FileLock(p):
        outcome = d.run_watch_cycle(source="claude-code", lock_path=p, idle_minutes=3)
    assert outcome.ran is False
    assert outcome.skipped_reason == "locked"
