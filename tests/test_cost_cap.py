"""`synapse_memory.cost.cap` — 월 비용 cap 가드 테스트.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import datetime
from unittest import mock

import pytest

from synapse_memory.cost.cap import (
    CAP_EXCEEDED_EXIT_CODE,
    FORCE_ENV_VAR,
    CapStatus,
    compute_month_to_date_usd,
    enforce_cost_cap,
    get_cap_status,
)
from synapse_memory.cost.events import CostEvent


def _event(ts: str, usd: float) -> CostEvent:
    return CostEvent(
        event_id="evt-test",
        ts=ts,
        command="ask",
        provider="claude",
        model="sonnet",
        status="success",
        input_tokens=100,
        output_tokens=100,
        usd=usd,
        pricing_source="static",
        elapsed_s=1.0,
    )


def test_compute_mtd_sums_current_month_only():
    now = datetime.datetime(2026, 5, 15, 12, 0, tzinfo=datetime.UTC)
    events = [
        _event("2026-05-01T08:00:00+00:00", 1.0),
        _event("2026-05-13T12:00:00+00:00", 0.5),
        _event("2026-04-30T23:59:59+00:00", 99.0),  # 전월 — 제외
        _event("2026-06-01T00:00:00+00:00", 99.0),  # 차월 — 제외
    ]
    with mock.patch(
        "synapse_memory.cost.cap.load_cost_events", return_value=events
    ):
        total = compute_month_to_date_usd(now=now)
    assert total == pytest.approx(1.5)


def test_compute_mtd_returns_zero_on_load_failure():
    with mock.patch(
        "synapse_memory.cost.cap.load_cost_events",
        side_effect=OSError("no file"),
    ):
        assert compute_month_to_date_usd() == 0.0


def test_get_cap_status_uses_config_value():
    with mock.patch(
        "synapse_memory.cost.cap.load_cost_events", return_value=[]
    ), mock.patch(
        "synapse_memory.cost.cap.compute_month_to_date_usd", return_value=5.0
    ), mock.patch("synapse_memory.config.get_config") as get_cfg:
        cfg = mock.MagicMock()
        cfg.cost.monthly_cap_usd = 10.0
        get_cfg.return_value = cfg
        status = get_cap_status()
    assert status.cap_usd == 10.0
    assert status.month_to_date_usd == 5.0
    assert status.over_cap is False
    assert status.usage_ratio == 0.5
    assert status.remaining_usd == 5.0


def test_cap_status_over_cap_when_mtd_at_or_above_limit():
    s = CapStatus(cap_usd=10.0, month_to_date_usd=10.0)
    assert s.over_cap is True
    s2 = CapStatus(cap_usd=10.0, month_to_date_usd=15.0)
    assert s2.over_cap is True


def test_cap_status_null_cap_means_unlimited():
    s = CapStatus(cap_usd=None, month_to_date_usd=999.0)
    assert s.over_cap is False
    assert s.usage_ratio == 0.0
    assert s.remaining_usd == float("inf")


def test_enforce_passes_when_cap_is_none():
    with mock.patch(
        "synapse_memory.cost.cap.get_cap_status",
        return_value=CapStatus(cap_usd=None, month_to_date_usd=100.0),
    ):
        enforce_cost_cap("ask")


def test_enforce_blocks_when_over_cap(capsys, monkeypatch):
    monkeypatch.delenv(FORCE_ENV_VAR, raising=False)
    with mock.patch(
        "synapse_memory.cost.cap.get_cap_status",
        return_value=CapStatus(cap_usd=10.0, month_to_date_usd=11.0),
    ), pytest.raises(SystemExit) as exc:
        enforce_cost_cap("ask")
    assert exc.value.code == CAP_EXCEEDED_EXIT_CODE
    err = capsys.readouterr().err
    assert "월 cap 초과" in err
    assert "$10.00" in err


def test_enforce_passes_when_force_env_set(capsys, monkeypatch):
    monkeypatch.setenv(FORCE_ENV_VAR, "1")
    with mock.patch(
        "synapse_memory.cost.cap.get_cap_status",
        return_value=CapStatus(cap_usd=10.0, month_to_date_usd=11.0),
    ):
        enforce_cost_cap("ask")
    err = capsys.readouterr().err
    assert "초과" in err
    assert FORCE_ENV_VAR in err


def test_enforce_warns_at_80_percent(capsys, monkeypatch):
    monkeypatch.delenv(FORCE_ENV_VAR, raising=False)
    with mock.patch(
        "synapse_memory.cost.cap.get_cap_status",
        return_value=CapStatus(cap_usd=10.0, month_to_date_usd=8.5),
    ):
        enforce_cost_cap("ask")
    err = capsys.readouterr().err
    assert "사용량" in err


def test_enforce_silent_under_80_percent(capsys, monkeypatch):
    monkeypatch.delenv(FORCE_ENV_VAR, raising=False)
    with mock.patch(
        "synapse_memory.cost.cap.get_cap_status",
        return_value=CapStatus(cap_usd=10.0, month_to_date_usd=5.0),
    ):
        enforce_cost_cap("ask")
    err = capsys.readouterr().err
    assert err == ""


def test_month_window_handles_december_year_rollover():
    now = datetime.datetime(2026, 12, 31, 23, 59, tzinfo=datetime.UTC)
    events = [
        _event("2026-12-15T00:00:00+00:00", 2.0),
        _event("2027-01-01T00:00:01+00:00", 99.0),
    ]
    with mock.patch(
        "synapse_memory.cost.cap.load_cost_events", return_value=events
    ):
        total = compute_month_to_date_usd(now=now)
    assert total == pytest.approx(2.0)
