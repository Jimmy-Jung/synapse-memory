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
    collect_review_candidates,
    enrich_promoted_patterns,
    find_entry,
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


# ---------------------------------------------------------------------------
# find_entry — Jaccard 의미 매칭 (fingerprint dispersion 완화)
# ---------------------------------------------------------------------------


class TestFindEntry:
    def test_exact_fingerprint_match(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [_fact("Rust 학습")], [], today=datetime.date(2026, 5, 18)
        )
        entry = find_entry(ledger, "fact", "Rust 학습")
        assert entry is not None
        assert entry.seen_count == 1

    def test_jaccard_fallback_match(self) -> None:
        """토큰 셋이 75% 이상 겹치면 같은 entry 로 매칭."""
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("Swift 6 동시성 모델 학습")],
            [],
            today=datetime.date(2026, 5, 18),
        )
        # 4 token 중 3 매치 (Swift / 6 / 학습) → Jaccard 3/4 = 0.75 ≥ 임계치
        entry = find_entry(ledger, "fact", "Swift 6 동시성 학습")
        assert entry is not None
        assert entry.fingerprint == "swift 6 동시성 모델 학습"

    def test_no_match_returns_none(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [_fact("Rust 학습")], [], today=datetime.date(2026, 5, 18)
        )
        assert find_entry(ledger, "fact", "전혀 다른 주제") is None

    def test_kind_isolation(self) -> None:
        """같은 statement 라도 kind 가 다르면 별개로 매칭."""
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("같은 텍스트")],
            [_pattern("같은 텍스트")],
            today=datetime.date(2026, 5, 18),
        )
        fact_e = find_entry(ledger, "fact", "같은 텍스트")
        pattern_e = find_entry(ledger, "pattern", "같은 텍스트")
        assert fact_e is not None
        assert pattern_e is not None
        assert fact_e is not pattern_e

    def test_empty_statement_returns_none(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [_fact("X")], [], today=datetime.date(2026, 5, 18)
        )
        assert find_entry(ledger, "fact", "   ") is None


# ---------------------------------------------------------------------------
# fingerprint dispersion 통합 시나리오 — 표현 변동에도 seen_count 누적
# ---------------------------------------------------------------------------


class TestFingerprintDispersion:
    def test_accumulates_across_paraphrased_statements(self) -> None:
        """LLM 이 같은 관점을 매일 다른 표현으로 뽑아도 한 entry 로 누적."""
        ledger: dict[str, LedgerEntry] = {}
        paraphrases = [
            ("2026-05-15", "Swift 6 동시성 모델 학습"),
            ("2026-05-16", "Swift 6 동시성 학습"),  # token 일부 누락
            ("2026-05-17", "Swift 6 동시성 모델을 학습"),  # 조사 추가
        ]
        for day, stmt in paraphrases:
            record_extraction(
                ledger,
                [_fact(stmt)],
                [],
                today=datetime.date.fromisoformat(day),
            )
        # entry 하나로 흡수
        assert len(ledger) == 1
        entry = next(iter(ledger.values()))
        assert entry.seen_count == 3
        assert entry.first_seen == "2026-05-15"
        assert entry.last_seen == "2026-05-17"
        # statements 누적 — 표현 변종이 모두 보관
        assert len(entry.statements) == 3

    def test_promote_uses_aggregated_seen_count(self) -> None:
        """흡수된 누적 덕에 min_count=3 임계치 통과."""
        ledger: dict[str, LedgerEntry] = {}
        for day, stmt in [
            ("2026-05-15", "Swift 6 동시성 모델 학습"),
            ("2026-05-16", "Swift 6 동시성 학습"),
            ("2026-05-17", "Swift 6 동시성 모델을 학습"),
        ]:
            record_extraction(
                ledger, [_fact(stmt, conf=0.8)], [],
                today=datetime.date.fromisoformat(day),
            )
        facts, _, report = promote_candidates(
            ledger,
            facts_input=[_fact("Swift 6 동시성 학습", conf=0.8)],
            patterns_input=[],
            min_count=3, window_days=14, fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 17),
        )
        assert len(facts) == 1
        assert report.promoted_fact_count == 1

    def test_mark_promoted_finds_absorbed_entry(self) -> None:
        """promoted ProfileFact (best_statement) 로 흡수된 entry 를 표시."""
        ledger: dict[str, LedgerEntry] = {}
        for day, stmt in [
            ("2026-05-15", "Swift 6 동시성 모델 학습"),
            ("2026-05-16", "Swift 6 동시성 학습"),
            ("2026-05-17", "Swift 6 동시성 모델을 학습"),
        ]:
            record_extraction(
                ledger, [_fact(stmt, conf=0.8)], [],
                today=datetime.date.fromisoformat(day),
            )
        facts, _, _ = promote_candidates(
            ledger,
            facts_input=[_fact("Swift 6 동시성 학습", conf=0.8)],
            patterns_input=[],
            min_count=3, window_days=14, fast_path_confidence=0.95,
            today=datetime.date(2026, 5, 17),
        )
        # promoted ProfileFact 의 statement 는 entry.best_statement() — 최근 표현
        # → entry.fingerprint (첫 등장) 와 다를 수 있음. find_entry 가 매칭해줌.
        mark_promoted(ledger, facts, [], today=datetime.date(2026, 5, 17))
        entry = next(iter(ledger.values()))
        assert entry.promoted is True
        assert entry.promoted_at == "2026-05-17"


# ---------------------------------------------------------------------------
# P2 — fast_path_confidence 0.90 기본값 회귀
# ---------------------------------------------------------------------------


class TestCollectReviewCandidates:
    """daily 가 0건으로 끝났을 때 임계치 완화 검토 보조 경로."""

    def test_filters_by_min_confidence(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        for day, stmt, conf in [
            ("2026-05-15", "A 후보", 0.92),  # 통과
            ("2026-05-16", "B 후보", 0.86),  # 통과
            ("2026-05-17", "C 후보", 0.72),  # 임계치 미달
        ]:
            record_extraction(
                ledger, [_fact(stmt, conf=conf)], [],
                today=datetime.date.fromisoformat(day),
            )
        facts, patterns = collect_review_candidates(
            ledger,
            min_confidence=0.85,
            window_days=14,
            today=datetime.date(2026, 5, 18),
        )
        statements = {f.statement for f in facts}
        assert statements == {"A 후보", "B 후보"}
        assert patterns == []

    def test_excludes_promoted(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [_fact("X", conf=0.92)], [],
            today=datetime.date(2026, 5, 18),
        )
        entry = next(iter(ledger.values()))
        entry.promoted = True
        facts, _ = collect_review_candidates(
            ledger, min_confidence=0.85, window_days=14,
            today=datetime.date(2026, 5, 18),
        )
        assert facts == []

    def test_excludes_out_of_window(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [_fact("옛 후보", conf=0.92)], [],
            today=datetime.date(2026, 4, 1),  # 47일 전
        )
        facts, _ = collect_review_candidates(
            ledger, min_confidence=0.85, window_days=14,
            today=datetime.date(2026, 5, 18),
        )
        assert facts == []

    def test_pattern_carried_over(self) -> None:
        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger, [],
            [_pattern("패턴 후보", conf=0.88)],
            today=datetime.date(2026, 5, 18),
        )
        facts, patterns = collect_review_candidates(
            ledger, min_confidence=0.85, window_days=14,
            today=datetime.date(2026, 5, 18),
        )
        assert facts == []
        assert len(patterns) == 1
        assert patterns[0].trigger == "패턴 후보"


class TestFastPathThreshold:
    def test_default_threshold_promotes_at_0_90(self) -> None:
        """config 기본값 0.90 — 단일 호출 confidence 0.90 도 fast path 통과."""
        from synapse_memory.config import ProfileConfig

        assert ProfileConfig.fast_path_confidence == 0.90

        ledger: dict[str, LedgerEntry] = {}
        record_extraction(
            ledger,
            [_fact("매우 확신", conf=0.90)],
            [],
            today=datetime.date(2026, 5, 18),
        )
        facts, _, _ = promote_candidates(
            ledger,
            facts_input=[_fact("매우 확신", conf=0.90)],
            patterns_input=[],
            min_count=3, window_days=14,
            fast_path_confidence=ProfileConfig.fast_path_confidence,
            today=datetime.date(2026, 5, 18),
        )
        assert len(facts) == 1
