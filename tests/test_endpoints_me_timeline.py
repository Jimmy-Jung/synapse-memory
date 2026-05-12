"""Timeline recall tests — FR-001~FR-017.

본 모듈은 `synapse-memory me what-did-i-think --timeline` 의 시간축 정렬 ·
분기 그룹화 · 폴백 · 모드 별칭 · 회귀 가드를 검증한다.

매핑:
- spec: ``specs/002-timeline-recall/spec.md`` (User Story 1/2/3, FR-001~017)
- plan: ``specs/002-timeline-recall/plan.md``
- contracts: ``specs/002-timeline-recall/contracts/cli-contracts.md``
- data-model: ``specs/002-timeline-recall/data-model.md``

테스트는 tasks.md T008~T016, T025~T026, T033~T036, T044 에서 채워진다.
본 파일은 T001 (skeleton) 으로 import 만 정의한다.
"""

from __future__ import annotations

import datetime as _datetime
import json
from pathlib import Path

import pytest

from synapse_memory.endpoints.me import (
    _format_timeline_output,
    _group_by_quarter,
    _resolve_sort_ts,
    _sort_by_time,
)

__all__: list[str] = []  # tests are discovered by pytest, not imported elsewhere

GOLDEN_PATH = (
    Path(__file__).parent / "golden" / "timeline_recall" / "synthetic_30.json"
)


@pytest.fixture
def today() -> _datetime.date:
    """Deterministic 'today' for tests dependent on FR-003 today_fallback."""
    return _datetime.date(2026, 5, 12)


def _kendall_tau(a: list[str], b: list[str]) -> float:
    """Pure-python Kendall τ for two equal-length ranked sequences.

    Implemented inline to avoid scipy dep. Spec SC-001 requires τ ≥ 0.9.
    """
    n = len(a)
    assert len(b) == n, "sequences must be equal length"
    if n < 2:
        return 1.0
    rank_b = {v: i for i, v in enumerate(b)}
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            ai, aj = a[i], a[j]
            if ai not in rank_b or aj not in rank_b:
                continue
            sgn_a = -1  # ai precedes aj in a → "earlier" rank
            sgn_b = rank_b[ai] - rank_b[aj]
            if sgn_b == 0:
                continue
            if (sgn_a < 0) == (sgn_b < 0):
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return 1.0 if total == 0 else (concordant - discordant) / total


# ---------------------------------------------------------------------------
# T008 — FR-002: period_end desc 1차, created desc 2차
# ---------------------------------------------------------------------------


def test_timeline_basic_sort(today: _datetime.date) -> None:
    """FR-002 — period_end desc 1차, 동률 시 created desc 2차."""
    meta_old = {
        "card_id": "old",
        "source_kind": "card_project",
        "period_end": "2024-03-15",
        "created": "2024-01-01",
        "status": "archived",
    }
    meta_new = {
        "card_id": "new",
        "source_kind": "card_project",
        "period_end": "2025-02-15",
        "created": "2024-12-01",
        "status": "archived",
    }
    cards = [
        _resolve_sort_ts(meta_old, today, distance=0.5),
        _resolve_sort_ts(meta_new, today, distance=0.3),
    ]
    sorted_cards = _sort_by_time(cards)
    assert [c.card_id for c in sorted_cards] == ["new", "old"]


# ---------------------------------------------------------------------------
# T009 — FR-003: active + period_end null → today_fallback
# ---------------------------------------------------------------------------


def test_period_end_null_active(today: _datetime.date) -> None:
    """FR-003 — period_end null + status=active → sort_ts = today, label '오늘'."""
    meta = {
        "card_id": "active_one",
        "source_kind": "card_project",
        "period_end": None,
        "created": "2024-08-30",
        "status": "active",
    }
    card = _resolve_sort_ts(meta, today, distance=0.4)
    assert card.sort_ts_source == "today_fallback"
    assert card.sort_ts.date() == today


# ---------------------------------------------------------------------------
# T010 — FR-004: non-active + period_end null → created fallback
# ---------------------------------------------------------------------------


def test_period_end_null_inactive(today: _datetime.date) -> None:
    """FR-004 — period_end null + status≠active → sort_ts = created."""
    meta = {
        "card_id": "archived_one",
        "source_kind": "card_project",
        "period_end": None,
        "created": "2023-06-15",
        "status": "archived",
    }
    card = _resolve_sort_ts(meta, today, distance=0.4)
    assert card.sort_ts_source == "created"
    assert card.sort_ts.date() == _datetime.date(2023, 6, 15)


# ---------------------------------------------------------------------------
# T011 — FR-005: CompanyCard → last_reviewed
# ---------------------------------------------------------------------------


def test_company_card_uses_last_reviewed(today: _datetime.date) -> None:
    """FR-005 — CompanyCard 는 last_reviewed 를 정렬 키로 사용."""
    meta = {
        "card_id": "회사A",
        "source_kind": "card_company",
        "last_reviewed": "2025-03-10",
        "created": "2024-01-01",
    }
    card = _resolve_sort_ts(meta, today, distance=0.4)
    assert card.sort_ts_source == "last_reviewed"
    assert card.sort_ts.date() == _datetime.date(2025, 3, 10)


# ---------------------------------------------------------------------------
# T012 — FR-006: 분기 헤더 포맷 "## 2024 Q3" (RT-3)
# ---------------------------------------------------------------------------


def test_quarter_group_header(today: _datetime.date) -> None:
    """FR-006 + RT-3 — 분기 헤더가 정확히 '## 2024 Q3' 포맷."""
    cards = [
        _resolve_sort_ts(
            {
                "card_id": "a",
                "source_kind": "card_project",
                "period_end": "2024-08-10",
                "created": "2024-01-01",
                "status": "archived",
            },
            today,
            distance=0.5,
        ),
        _resolve_sort_ts(
            {
                "card_id": "b",
                "source_kind": "card_project",
                "period_end": "2024-11-20",
                "created": "2024-04-01",
                "status": "archived",
            },
            today,
            distance=0.4,
        ),
    ]
    groups = _group_by_quarter(_sort_by_time(cards))
    labels = [g.quarter_label for g in groups]
    assert "2024 Q4" in labels
    assert "2024 Q3" in labels
    # 그룹 자체는 sort_ts desc 이므로 Q4 가 Q3 보다 앞.
    assert labels.index("2024 Q4") < labels.index("2024 Q3")
    output = _format_timeline_output(groups, limit=20)
    assert "## 2024 Q4" in output
    assert "## 2024 Q3" in output


# ---------------------------------------------------------------------------
# T013 — FR-007: 동일 분기 ≥ 2 카드 시 월 서브헤더 "### 2024-09"
# ---------------------------------------------------------------------------


def test_month_subheader(today: _datetime.date) -> None:
    """FR-007 — 같은 분기 안에 다른 월의 카드 ≥ 2 → 월 서브헤더 출력."""
    cards = [
        _resolve_sort_ts(
            {
                "card_id": "aug",
                "source_kind": "card_project",
                "period_end": "2024-08-10",
                "created": "2024-01-01",
                "status": "archived",
            },
            today,
            distance=0.5,
        ),
        _resolve_sort_ts(
            {
                "card_id": "sep",
                "source_kind": "card_project",
                "period_end": "2024-09-25",
                "created": "2024-02-01",
                "status": "archived",
            },
            today,
            distance=0.4,
        ),
    ]
    groups = _group_by_quarter(_sort_by_time(cards))
    output = _format_timeline_output(groups, limit=20)
    assert "### 2024-09" in output
    assert "### 2024-08" in output


# ---------------------------------------------------------------------------
# T014 — FR-008: 단일 카드 시 헤더 없음
# ---------------------------------------------------------------------------


def test_single_result_no_header(today: _datetime.date) -> None:
    """FR-008 — 카드 1개만 결과인 경우 분기/월 헤더 출력 안 함."""
    card = _resolve_sort_ts(
        {
            "card_id": "solo",
            "source_kind": "card_project",
            "period_end": "2025-02-15",
            "created": "2024-12-01",
            "status": "archived",
        },
        today,
        distance=0.4,
    )
    groups = _group_by_quarter([card])
    output = _format_timeline_output(groups, limit=20)
    assert "## " not in output
    assert "### " not in output
    assert "solo" in output


# ---------------------------------------------------------------------------
# T015 — RT-2: YYYY-MM 입력의 월 말일 정규화 (+ leap year)
# ---------------------------------------------------------------------------


def test_yyyy_mm_normalization(today: _datetime.date) -> None:
    """RT-2 — period_end='YYYY-MM' → 해당 월의 마지막 날로 정규화."""
    # 2024-02 = 윤년 → 29일
    card_feb = _resolve_sort_ts(
        {
            "card_id": "feb",
            "source_kind": "card_project",
            "period_end": "2024-02",
            "created": "2023-12-01",
            "status": "archived",
        },
        today,
        distance=0.4,
    )
    assert card_feb.sort_ts.date() == _datetime.date(2024, 2, 29)
    # 2023-02 = 평년 → 28일
    card_feb_nonleap = _resolve_sort_ts(
        {
            "card_id": "feb_2023",
            "source_kind": "card_project",
            "period_end": "2023-02",
            "created": "2022-12-01",
            "status": "archived",
        },
        today,
        distance=0.4,
    )
    assert card_feb_nonleap.sort_ts.date() == _datetime.date(2023, 2, 28)
    # 2024-04 = 30일
    card_apr = _resolve_sort_ts(
        {
            "card_id": "apr",
            "source_kind": "card_project",
            "period_end": "2024-04",
            "created": "2024-01-01",
            "status": "archived",
        },
        today,
        distance=0.4,
    )
    assert card_apr.sort_ts.date() == _datetime.date(2024, 4, 30)


# ---------------------------------------------------------------------------
# T016 — SC-001: Kendall τ ≥ 0.9 on synthetic_30.json
# ---------------------------------------------------------------------------


def test_kendall_tau_golden(today: _datetime.date) -> None:
    """SC-001 — 30 query 골든셋에서 Kendall τ ≥ 0.9."""
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    tau_values: list[float] = []
    for q in data["queries"]:
        cards = [
            _resolve_sort_ts(meta, today, distance=0.5 + i * 0.01)
            for i, meta in enumerate(q["cards"])
        ]
        sorted_cards = _sort_by_time(cards)
        observed = [c.card_id for c in sorted_cards]
        expected = list(q["expected_card_id_order"])
        tau = _kendall_tau(observed, expected)
        tau_values.append(tau)
    avg = sum(tau_values) / len(tau_values)
    assert avg >= 0.9, (
        f"Average Kendall τ={avg:.4f} below 0.9 across {len(tau_values)} queries"
    )


# ---------------------------------------------------------------------------
# Integration helpers — what_did_i_think() with mocked store/claude
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch  # noqa: E402  (kept near integration tests)

import synapse_memory.endpoints.me as me_mod  # noqa: E402
from synapse_memory.endpoints.me import what_did_i_think  # noqa: E402
from synapse_memory.rag.vector_store import VectorRecord  # noqa: E402


def _record(card_id: str, *, meta: dict[str, str] | None = None, doc: str = "") -> VectorRecord:
    base_meta = {
        "source_kind": "card_project",
        "card_id": card_id,
        "display_name": card_id,
    }
    if meta:
        base_meta.update(meta)
    return VectorRecord(
        id=f"{base_meta['source_kind']}:{card_id}",
        document=doc or f"# {card_id}",
        embedding=[0.0],
        metadata=base_meta,
    )


# ---------------------------------------------------------------------------
# T025 — FR-011: 결과 0건 메시지 + exit 0 의도
# ---------------------------------------------------------------------------


def test_empty_result_message(today: _datetime.date) -> None:
    """FR-011 — store.query 가 빈 결과 → 안내 메시지 + 빈 source_ids."""
    store = MagicMock()
    store.query.return_value = []
    with patch.object(me_mod, "embed_query", return_value=[0.0]):
        result = what_did_i_think("nothing", store=store, by="time", today=today)
    assert result.source_ids == []
    assert "관련 카드 없음" in result.answer
    assert "`synapse-memory daily`" in result.answer


# ---------------------------------------------------------------------------
# T026 — FR-012: 모든 메타 null → distance 폴백 헤더 + distance asc
# ---------------------------------------------------------------------------


def test_all_meta_null_fallback(today: _datetime.date) -> None:
    """FR-012 — period_end/created/last_reviewed 모두 부재 → 폴백 헤더 + distance asc."""
    store = MagicMock()
    store.query.return_value = [
        (_record("c1", meta={"period_end": "", "created": "", "last_reviewed": ""}), 0.6),
        (_record("c2", meta={"period_end": "", "created": "", "last_reviewed": ""}), 0.3),
        (_record("c3", meta={"period_end": "", "created": "", "last_reviewed": ""}), 0.45),
    ]
    with patch.object(me_mod, "embed_query", return_value=[0.0]):
        result = what_did_i_think("x", store=store, by="time", today=today)
    out = result.answer
    assert "## 시간 정보 없음 — distance 순 폴백" in out
    # distance asc → c2 (0.3) → c3 (0.45) → c1 (0.6)
    assert out.index("**c2**") < out.index("**c3**") < out.index("**c1**")


# ---------------------------------------------------------------------------
# T033 — FR-009: --by time 출력 == --timeline 출력 (시맨틱 일치)
# ---------------------------------------------------------------------------


def test_by_time_alias(today: _datetime.date) -> None:
    """FR-009 — by='time' 호출이 timeline 모드와 동일 결과."""
    store = MagicMock()
    store.query.return_value = [
        (_record("a", meta={"period_end": "2024-08-10", "created": "2024-01-01", "status": "archived"}), 0.5),
        (_record("b", meta={"period_end": "2024-11-20", "created": "2024-04-01", "status": "archived"}), 0.4),
    ]
    with patch.object(me_mod, "embed_query", return_value=[0.0]):
        r_by_time = what_did_i_think("x", store=store, by="time", today=today)
    # 두 번째 호출에 새 mock — same return
    store2 = MagicMock()
    store2.query.return_value = [
        (_record("a", meta={"period_end": "2024-08-10", "created": "2024-01-01", "status": "archived"}), 0.5),
        (_record("b", meta={"period_end": "2024-11-20", "created": "2024-04-01", "status": "archived"}), 0.4),
    ]
    with patch.object(me_mod, "embed_query", return_value=[0.0]):
        r_timeline = what_did_i_think("x", store=store2, by="time", today=today)
    assert r_by_time.answer == r_timeline.answer


# ---------------------------------------------------------------------------
# T034 — FR-009: --by distance 가 기존 cosine + Claude 거동
# ---------------------------------------------------------------------------


def test_by_distance_explicit(today: _datetime.date) -> None:
    """FR-009 — by='distance' 는 기존 Claude 통합 답변 반환."""
    store = MagicMock()
    store.query.return_value = [
        (_record("a", doc="# A\nbody a"), 0.5),
    ]
    with (
        patch.object(me_mod, "embed_query", return_value=[0.0]),
        patch.object(me_mod.ai_api, "complete", return_value="CLAUDE_ANSWER_DISTANCE"),
    ):
        result = what_did_i_think("x", store=store, by="distance", today=today)
    assert result.answer == "CLAUDE_ANSWER_DISTANCE"
    assert "a" in result.source_ids


# ---------------------------------------------------------------------------
# T035 — FR-009: cli 충돌 검증 (--timeline + --by distance → exit 1)
# ---------------------------------------------------------------------------


def test_conflict_timeline_and_by_distance(capsys: pytest.CaptureFixture[str]) -> None:
    """FR-009 — cli 레벨 --timeline + --by distance 충돌은 exit 1 + stderr."""
    import argparse

    from synapse_memory.cli import cmd_me_what_did_i_think

    ns = argparse.Namespace(
        topic="x", top_k=8, model="sonnet",
        timeline=True, by="distance", limit=20,
    )
    rc = cmd_me_what_did_i_think(ns)
    err = capsys.readouterr().err
    assert rc == 1
    assert "conflict" in err.lower()


# ---------------------------------------------------------------------------
# T036 — FR-010: --limit 기본 20, 범위 [1, 100], 외 → exit 2
# ---------------------------------------------------------------------------


def test_limit_default_and_override(today: _datetime.date) -> None:
    """FR-010 — limit 동작 (출력 카드 수) + 범위 검증."""
    # endpoint 함수 레벨: limit=2 → 상위 2 카드만
    store = MagicMock()
    store.query.return_value = [
        (_record(f"c{i}", meta={"period_end": f"2024-{12 - i:02d}-01", "created": "2024-01-01", "status": "archived"}), 0.5)
        for i in range(5)
    ]
    with patch.object(me_mod, "embed_query", return_value=[0.0]):
        result = what_did_i_think("x", store=store, by="time", limit=2, today=today)
    assert result.answer.count("**c") == 2

    # cli 레벨: limit=0 → exit 2
    import argparse

    from synapse_memory.cli import cmd_me_what_did_i_think

    ns = argparse.Namespace(
        topic="x", top_k=8, model="sonnet",
        timeline=False, by=None, limit=0,
    )
    rc = cmd_me_what_did_i_think(ns)
    assert rc == 2


# ---------------------------------------------------------------------------
# T043 — FR-013 + SC-004: distance 모드 회귀 가드 (기본 호출 = v0.4 동일)
# ---------------------------------------------------------------------------


def test_distance_regression_default(today: _datetime.date) -> None:
    """FR-013 — by 미지정 호출이 v0.4 와 동일하게 AI 답변을 그대로 반환.

    회귀 가드: timeline 변경이 distance branch 의 동작·answer 형태를 깨지 않음.
    """
    store = MagicMock()
    store.query.return_value = [
        (_record("a", doc="# A"), 0.4),
        (_record("b", doc="# B"), 0.5),
    ]
    with (
        patch.object(me_mod, "embed_query", return_value=[0.0]),
        patch.object(
            me_mod.ai_api, "complete", return_value="**핵심.** 자세한 정리…"
        ) as mock_ai,
    ):
        result = what_did_i_think("x", store=store)  # by 인자 미지정 → "distance"
    # AI provider가 정확히 한 번 호출됨 + answer 가 그대로 전달됨
    assert mock_ai.call_count == 1
    assert result.answer == "**핵심.** 자세한 정리…"
    assert result.source_ids == ["a", "b"]


# ---------------------------------------------------------------------------
# T044 — FR-016 (헌법 §II): timeline 모드는 외부 LLM 호출 안 함
# ---------------------------------------------------------------------------


def test_no_raw_in_prompt(today: _datetime.date) -> None:
    """FR-016 — by='time' 모드는 AI wrapper 를 호출하지 않음 (자명한 prompt 차단).

    AI provider 호출이 발생하면 raw PII 가 외부로 나갈 가능성이 생기지만, timeline
    모드는 RAG 결과만 로컬에서 markdown 으로 정리하므로 호출 자체가 0.
    """
    store = MagicMock()
    store.query.return_value = [
        (_record("a", meta={"period_end": "2024-08-10", "created": "2024-01-01", "status": "archived"}, doc="# A"), 0.5),
    ]
    with (
        patch.object(me_mod, "embed_query", return_value=[0.0]),
        patch.object(me_mod.ai_api, "complete") as mock_ai,
    ):
        what_did_i_think("x", store=store, by="time", today=today)
    assert mock_ai.call_count == 0, (
        f"timeline mode must NOT call AI provider (got {mock_ai.call_count} call(s))"
    )
