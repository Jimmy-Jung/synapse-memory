"""``synapse_memory.status`` — daily 진행률 status writer/reader 테스트.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import itertools
import json

import pytest

from synapse_memory.status import (
    DailyStatus,
    StatusSink,
    StatusWriter,
    read_status,
    render_status,
)


@pytest.fixture
def fake_clock():
    counter = itertools.count(1)

    def _clock() -> str:
        return f"2026-05-13T00:00:{next(counter):02d}+00:00"

    return _clock


def test_status_writer_initial_file_has_running_state(tmp_path, fake_clock):
    path = tmp_path / "daily.status.json"
    writer = StatusWriter(total_stages=7, path=path, clock=fake_clock, pid=42)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["state"] == "running"
    assert payload["pid"] == 42
    assert payload["total_stages"] == 7
    assert payload["current_stage"] == ""
    assert payload["started_at"] == "2026-05-13T00:00:01+00:00"
    assert payload["updated_at"] == "2026-05-13T00:00:01+00:00"
    assert writer.status.state == "running"


def test_status_writer_records_stage_and_item_lifecycle(tmp_path, fake_clock):
    path = tmp_path / "daily.status.json"
    writer = StatusWriter(total_stages=7, path=path, clock=fake_clock, pid=42)

    writer.begin_stage("generate", index=4)
    writer.update_item(index=3, total=27, label="kakaobank-2026 (company)")
    mid = json.loads(path.read_text(encoding="utf-8"))
    assert mid["current_stage"] == "generate"
    assert mid["current_stage_index"] == 4
    assert mid["current_item"] == "kakaobank-2026 (company)"
    assert mid["current_item_index"] == 3
    assert mid["current_item_total"] == 27

    writer.end_stage("generate", failed=False)
    end = json.loads(path.read_text(encoding="utf-8"))
    assert end["completed_stages"] == ["generate"]
    assert end["failed_stages"] == []
    assert end["current_item"] == ""
    assert end["current_item_index"] == 0


def test_status_writer_finish_sets_done_and_failed(tmp_path, fake_clock):
    path = tmp_path / "daily.status.json"
    writer = StatusWriter(total_stages=7, path=path, clock=fake_clock, pid=42)

    writer.begin_stage("classify", index=3)
    writer.end_stage("classify", failed=True)
    writer.finish(errors=1)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["state"] == "failed"
    assert payload["failed_stages"] == ["classify"]
    assert payload["current_stage"] == ""

    path2 = tmp_path / "daily2.status.json"
    writer2 = StatusWriter(total_stages=7, path=path2, clock=fake_clock, pid=42)
    writer2.finish(errors=0)
    assert json.loads(path2.read_text(encoding="utf-8"))["state"] == "done"


def test_status_writer_swallows_io_errors(tmp_path, fake_clock, monkeypatch):
    """write 실패가 예외로 propagate되면 daily 실행이 멈춘다 — 반드시 swallow."""
    path = tmp_path / "daily.status.json"
    writer = StatusWriter(total_stages=7, path=path, clock=fake_clock, pid=42)

    def boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr("synapse_memory.status.tempfile.NamedTemporaryFile", boom)

    writer.begin_stage("generate", index=4)
    writer.update_item(index=1, total=2, label="x")
    writer.end_stage("generate")
    writer.finish(errors=0)


def test_read_status_returns_none_when_file_missing(tmp_path):
    assert read_status(path=tmp_path / "missing.json") is None


def test_read_status_returns_none_on_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not json {", encoding="utf-8")
    assert read_status(path=path) is None


def test_read_status_roundtrip(tmp_path, fake_clock):
    path = tmp_path / "daily.status.json"
    writer = StatusWriter(total_stages=7, path=path, clock=fake_clock, pid=42)
    writer.begin_stage("generate", index=4)
    writer.update_item(index=8, total=27, label="kakaobank-2026 (company)")

    loaded = read_status(path=path)
    assert isinstance(loaded, DailyStatus)
    assert loaded.current_stage == "generate"
    assert loaded.current_item_total == 27


def test_render_status_handles_none():
    out = render_status(None)
    assert "없음" in out


def test_render_status_includes_progress_percentage():
    status = DailyStatus(
        pid=42,
        started_at="2026-05-13T00:00:01+00:00",
        updated_at="2026-05-13T00:00:10+00:00",
        state="running",
        current_stage="generate",
        current_stage_index=4,
        total_stages=7,
        current_item="kakaobank-2026 (company)",
        current_item_index=3,
        current_item_total=27,
        completed_stages=["classify"],
    )
    out = render_status(status)
    assert "generate (4/7)" in out
    assert "kakaobank-2026 (company)" in out
    assert "[3/27, 11%]" in out
    assert "completed: classify" in out


def test_status_sink_is_noop():
    """StatusSink 기본 구현은 부작용이 없어야 한다 — 인자만 받고 끝."""
    sink = StatusSink()
    sink.begin_stage("x", 1)
    sink.update_item(index=1, total=1, label="y")
    sink.end_stage("x", failed=False)
    sink.finish(errors=0)


def test_run_daily_writes_status_via_default_sink(tmp_path, monkeypatch):
    """run_daily 기본 호출에서 status 파일이 자동 생성/갱신되는지 확인."""
    from synapse_memory import status as status_mod
    from synapse_memory.daily import run_daily

    status_path = tmp_path / "daily.status.json"
    monkeypatch.setattr(status_mod, "STATUS_FILE", status_path)

    result = run_daily(
        only={"report"},
        on_log=lambda _line: None,
        stage_actions={"report": lambda: "ok"},
    )
    assert result.errors == 0

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["state"] == "done"
    assert "report" in payload["completed_stages"]
