"""profile/ledger.py 테스트 — multi-day cross-validation + 누적 confidence.

핵심 시나리오
- record_extraction: 새 entry 생성, 기존 entry 누적
- statements/categories/confidence_history 누적 + 상한선
- promote_candidates: seen_count 임계치 + window 조건
- fast path: 단일 confidence ≥ fast_path_confidence 시 즉시 promote
- promoted=True entry 는 재promote 안 됨
- load/save round-trip
- enrich_promoted_patterns: action/rationale 보강

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from synapse_memory.profile.ledger import (
    LedgerEntry,
    enrich_promoted_patterns,
    load_ledger,
    mark_promoted,
    promote_candidates,
    record_extraction,
    save_ledger,
)
from synapse_memory.profile.schema import DecisionPattern, ProfileFact


def _fact(stmt: str, cat: str = "tech", conf: float = 0.8) -> ProfileFact:
    return ProfileFact(
        category=cat,
        statement=stmt,
        confidence=conf,
        source_ids=["t"],
        extracted_at="2026-05-18",
    )


def _pattern(trig: str, action: str = "a", conf: float = 0.8) -> DecisionPattern:
    return DecisionPattern(
        trigger=trig,
        action=action,
        rationale="r",
        confidence=conf,
        examples=["t"],
        extracted_at="2026-05-18",
    )


# ---------------------------------------------------------------------------
# LedgerEntry.record
# ---------------------------------------------------------------------------


class TestLedgerEntryRecord:
    def test_first_record_initializes(self) -> None:
        e = LedgerEntry(kind="fact", fingerprint="x")
        e.record(statement="X 원문", confidence=0.7, category="tech",
                 today="2026-05-18")
        assert e.first_seen == "2026-05-18"
        assert e.last_seen == "2026-05-18"
        assert e.seen_count == 1
        assert e.confidence_history == [0.7]
        assert e.statements == ["X 원문"]
        assert e.categories == ["tech"]

    def test_repeat_record_accumulates(self) -> None:
        e = LedgerEntry(
            kind="fact", fingerprint="x", first_seen="2026-05-15",
            last_seen="2026-05-15", seen_count=1,
            confidence_history=[0.7], statements=["X 원문"],
            categories=["tech"],
        )
        e.record(statement="X 변형 원문", confidence=0.85, category="preference",
                 today="2026-05-18")
        assert e.first_seen == "2026-05-15"  # 유지
        assert e.last_seen == "2026-05-18"
        assert e.seen_count == 2
        assert e.confidence_history == [0.7, 0.85]
        assert "X 변형 원문" in e.statements
        assert "preference" in e.categories

    def test_confidence_history_capped(self) -> None:
        e = LedgerEntry(kind="fact", fingerprint="x")
        for i in range(40):
            e.record(statement=f"v{i}", confidence=0.5, category="tech",
                     today="2026-05-18")
        assert len(e.confidence_history) == LedgerEntry._MAX_CONFIDENCE_HISTORY

    def test_statement_list_capped_keeps_recent(self) -> None:
        e = LedgerEntry(kind="fact", fingerprint="x")
        for i in range(10):
            e.record(statement=f"문장{i}", confidence=0.5, category="tech",
                     today="2026-05-18")
        assert len(e.statements) == LedgerEntry._MAX_STATEMENTS
        assert "문장9" in e.statements
        assert "문장0" not in e.statements


# ---------------------------------------------------------------------------
# record_extraction
# ---------------------------------------------------------------------------


class TestRecordExtraction:
    def test_creates_new_entries(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("Rust 학습", conf=0.7)],
            [_pattern("새 패턴", conf=0.6)],
            today=datetime.date(2026, 5, 18),
        )
        assert len(ledger) == 2
        fact_entry = next(e for e in ledger.values() if e.kind == "fact")
        assert fact_entry.seen_count == 1
        assert fact_entry.first_seen == "2026-05-18"

    def test_accumulates_across_days(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day in (15, 16, 17, 18):
            record_extraction(
                ledger,
                [_fact("Rust 학습", conf=0.7 + day * 0.01)],
                [],
                today=datetime.date(2026, 5, day),
            )
        entry = next(iter(ledger.values()))
        assert entry.seen_count == 4
        assert entry.first_seen == "2026-05-15"
        assert entry.last_seen == "2026-05-18"
        assert len(entry.confidence_history) == 4


# ---------------------------------------------------------------------------
# promote_candidates
# ---------------------------------------------------------------------------


class TestPromoteCandidates:
    def test_requires_min_count(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day in (16, 17):  # 2번만 등장
            record_extraction(
                ledger,
                [_fact("Rust 학습", conf=0.7)],
                [],
                today=datetime.date(2026, 5, day),
            )
        facts, _, report = promote_candidates(
            ledger,
            facts_input=[_fact("Rust 학습", conf=0.7)],
            patterns_input=[],
            min_count=3,
            window_days=14,
            fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 18),
        )
        assert facts == []
        assert report.awaiting_fact_count == 1
        assert report.promoted_fact_count == 0

    def test_promotes_after_min_count_in_window(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day in (15, 16, 17, 18):  # 4번 → min_count=3 충족
            record_extraction(
                ledger,
                [_fact("Rust 학습", conf=0.7)],
                [],
                today=datetime.date(2026, 5, day),
            )
        facts, _, report = promote_candidates(
            ledger,
            facts_input=[_fact("Rust 학습", conf=0.7)],
            patterns_input=[],
            min_count=3,
            window_days=14,
            fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 18),
        )
        assert len(facts) == 1
        assert facts[0].statement == "Rust 학습"
        assert report.promoted_fact_count == 1

    def test_out_of_window_not_promoted(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day in (1, 2, 3):  # 4월 — 14일 window 밖
            record_extraction(
                ledger,
                [_fact("옛 패턴", conf=0.7)],
                [],
                today=datetime.date(2026, 4, day),
            )
        facts, _, report = promote_candidates(
            ledger,
            facts_input=[],
            patterns_input=[],
            min_count=3,
            window_days=14,
            fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 18),
        )
        assert facts == []
        assert report.awaiting_fact_count == 1  # seen_count 충족하나 window 밖

    def test_fast_path_high_confidence(self) -> None:
        """단일 호출 confidence ≥ fast_path → 즉시 promote."""
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("매우 확신", conf=0.97)],
            [],
            today=datetime.date(2026, 5, 18),
        )
        facts, _, _ = promote_candidates(
            ledger,
            facts_input=[_fact("매우 확신", conf=0.97)],
            patterns_input=[],
            min_count=3,
            window_days=14,
            fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 18),
        )
        assert len(facts) == 1

    def test_already_promoted_skipped(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day in (15, 16, 17, 18):
            record_extraction(
                ledger,
                [_fact("Rust 학습", conf=0.7)],
                [],
                today=datetime.date(2026, 5, day),
            )
        facts1, _, _ = promote_candidates(
            ledger, facts_input=[], patterns_input=[],
            min_count=3, window_days=14, fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 18),
        )
        mark_promoted(ledger, facts1, [])
        facts2, _, report = promote_candidates(
            ledger, facts_input=[], patterns_input=[],
            min_count=3, window_days=14, fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 19),
        )
        assert facts2 == []
        assert report.promoted_fact_count == 0

    def test_patterns_use_trigger_fingerprint(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day in (15, 16, 17, 18):
            record_extraction(
                ledger,
                [],
                [_pattern("같은 trigger", action=f"act-{day}", conf=0.7)],
                today=datetime.date(2026, 5, day),
            )
        _, patterns, _ = promote_candidates(
            ledger, facts_input=[],
            patterns_input=[_pattern("같은 trigger", action="today-act", conf=0.7)],
            min_count=3, window_days=14, fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 18),
        )
        assert len(patterns) == 1
        assert patterns[0].trigger == "같은 trigger"


# ---------------------------------------------------------------------------
# enrich_promoted_patterns
# ---------------------------------------------------------------------------


class TestEnrichPromotedPatterns:
    def test_fills_action_from_today_call(self) -> None:
        promoted = [_pattern("trigger A", action="", conf=0.7)]
        today = [_pattern("trigger A", action="구체적 행동", conf=0.7)]
        enriched = enrich_promoted_patterns(promoted, today)
        assert enriched[0].action == "구체적 행동"
        assert enriched[0].trigger == "trigger A"

    def test_no_match_keeps_original(self) -> None:
        promoted = [_pattern("trigger A", action="", conf=0.7)]
        enriched = enrich_promoted_patterns(promoted, [])
        assert enriched[0].action == ""


# ---------------------------------------------------------------------------
# load / save round-trip
# ---------------------------------------------------------------------------


class TestLedgerPersistence:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "ledger.jsonl"
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("Rust 학습"), _fact("Go 학습")],
            [_pattern("새 패턴")],
            today=datetime.date(2026, 5, 18),
        )
        save_ledger(ledger, target)
        loaded = load_ledger(target)
        assert len(loaded) == 3
        fps_original = {(e.kind, e.fingerprint) for e in ledger.values()}
        fps_loaded = {(e.kind, e.fingerprint) for e in loaded.values()}
        assert fps_original == fps_loaded

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert load_ledger(tmp_path / "nope.jsonl") == {}

    def test_load_skips_malformed(self, tmp_path: Path) -> None:
        target = tmp_path / "ledger.jsonl"
        target.write_text(
            "not json\n"
            '{"kind": "invalid"}\n'
            '{"kind": "fact", "fingerprint": "x", "seen_count": 1}\n',
            encoding="utf-8",
        )
        loaded = load_ledger(target)
        assert len(loaded) == 1
        assert next(iter(loaded.values())).fingerprint == "x"

    def test_save_format_is_jsonl(self, tmp_path: Path) -> None:
        target = tmp_path / "ledger.jsonl"
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [_fact("X")], [], today=datetime.date(2026, 5, 18)
        )
        save_ledger(ledger, target)
        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["kind"] == "fact"
        assert data["seen_count"] == 1


# ---------------------------------------------------------------------------
# mark_promoted
# ---------------------------------------------------------------------------


class TestMarkPromoted:
    def test_marks_only_promoted(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("A"), _fact("B")],
            [],
            today=datetime.date(2026, 5, 18),
        )
        mark_promoted(
            ledger, [_fact("A")], [], today=datetime.date(2026, 5, 18)
        )
        a = ledger[next(k for k in ledger if "::a" in k)]
        b = ledger[next(k for k in ledger if "::b" in k)]
        assert a.promoted is True
        assert a.promoted_at == "2026-05-18"
        assert b.promoted is False
