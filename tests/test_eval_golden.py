"""골든셋 평가 모듈 테스트.

apfel 호출은 mock — 평가 로직(metric 계산, multi-set 매칭)만 검증.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_memory.eval.golden import (
    CategoryMetrics,
    _diff_multisets,
    default_synthetic_path,
    evaluate,
    load_golden_set,
)
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.redaction.pass1 import Detection, RedactionResult


def _ready_env() -> ApfelEnvironment:
    return ApfelEnvironment(
        apfel_path="/opt/homebrew/bin/apfel",
        apfel_version="apfel v1.3.3",
        macos_version="26.2",
        is_apple_silicon=True,
    )


# ---------------------------------------------------------------------------
# CategoryMetrics
# ---------------------------------------------------------------------------


class TestCategoryMetrics:
    def test_empty(self) -> None:
        m = CategoryMetrics()
        assert m.precision == 0.0
        assert m.recall == 0.0
        assert m.f1 == 0.0

    def test_perfect(self) -> None:
        m = CategoryMetrics(tp=10, fp=0, fn=0)
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0

    def test_only_fp(self) -> None:
        m = CategoryMetrics(tp=5, fp=5, fn=0)
        assert m.precision == 0.5
        assert m.recall == 1.0
        assert abs(m.f1 - 2 * 0.5 * 1.0 / 1.5) < 1e-9

    def test_only_fn(self) -> None:
        m = CategoryMetrics(tp=5, fp=0, fn=5)
        assert m.precision == 1.0
        assert m.recall == 0.5


# ---------------------------------------------------------------------------
# multi-set diff
# ---------------------------------------------------------------------------


class TestDiffMultisets:
    def test_perfect_match(self) -> None:
        det = Counter([("email", "a@b.com")])
        exp = Counter([("email", "a@b.com")])
        tp, fp, fn = _diff_multisets(det, exp)
        assert tp == Counter({("email", "a@b.com"): 1})
        assert fp == Counter()
        assert fn == Counter()

    def test_missing_detection_is_fn(self) -> None:
        det = Counter()
        exp = Counter([("email", "a@b.com")])
        tp, fp, fn = _diff_multisets(det, exp)
        assert tp == Counter()
        assert fp == Counter()
        assert fn == Counter({("email", "a@b.com"): 1})

    def test_extra_detection_is_fp(self) -> None:
        det = Counter([("email", "a@b.com")])
        exp = Counter()
        _tp, fp, _fn = _diff_multisets(det, exp)
        assert fp == Counter({("email", "a@b.com"): 1})

    def test_duplicate_count_handled(self) -> None:
        # detected: 3개, expected: 2개 → tp=2, fp=1
        det = Counter({("email", "x@y.com"): 3})
        exp = Counter({("email", "x@y.com"): 2})
        tp, fp, _fn = _diff_multisets(det, exp)
        assert tp[("email", "x@y.com")] == 2
        assert fp[("email", "x@y.com")] == 1


# ---------------------------------------------------------------------------
# load_golden_set
# ---------------------------------------------------------------------------


class TestLoadGoldenSet:
    def test_parses_samples(self, tmp_path: Path) -> None:
        path = tmp_path / "g.json"
        path.write_text(
            json.dumps(
                {
                    "samples": [
                        {
                            "id": "test-001",
                            "text": "hello",
                            "expected": [{"category": "x", "value": "y"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        samples = load_golden_set(path)
        assert len(samples) == 1
        assert samples[0]["id"] == "test-001"

    def test_missing_samples_key_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "g.json"
        path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="samples"):
            load_golden_set(path)


# ---------------------------------------------------------------------------
# evaluate (redact_full mock)
# ---------------------------------------------------------------------------


def _detection(category: str, matched: str, span: tuple[int, int] = (0, 0)) -> Detection:
    return Detection(
        category=category,
        span=span,
        matched=matched,
        placeholder=f"[{category.upper()}_1]",
    )


class TestEvaluate:
    def test_perfect_score(self) -> None:
        samples = [
            {
                "id": "s1",
                "text": "hello",
                "expected": [{"category": "email", "value": "a@b.com"}],
            }
        ]
        with patch("synapse_memory.eval.golden.redact_full") as mock_rf:
            mock_rf.return_value = RedactionResult(
                redacted="...",
                detections=[_detection("email", "a@b.com")],
            )
            result = evaluate(samples, env=_ready_env())

        assert result.overall.tp == 1
        assert result.overall.fp == 0
        assert result.overall.fn == 0
        assert result.samples_perfect == 1
        assert result.failures == []

    def test_false_positive(self) -> None:
        samples = [
            {"id": "s1", "text": "hello", "expected": []}
        ]
        with patch("synapse_memory.eval.golden.redact_full") as mock_rf:
            mock_rf.return_value = RedactionResult(
                redacted="...",
                detections=[_detection("email", "spurious@x.com")],
            )
            result = evaluate(samples, env=_ready_env())

        assert result.overall.fp == 1
        assert result.samples_perfect == 0
        assert len(result.failures) == 1
        assert result.failures[0].fp == [("email", "spurious@x.com")]

    def test_false_negative(self) -> None:
        samples = [
            {
                "id": "s1",
                "text": "hello",
                "expected": [{"category": "email", "value": "a@b.com"}],
            }
        ]
        with patch("synapse_memory.eval.golden.redact_full") as mock_rf:
            mock_rf.return_value = RedactionResult(
                redacted="...", detections=[]
            )
            result = evaluate(samples, env=_ready_env())

        assert result.overall.fn == 1
        assert result.failures[0].fn == [("email", "a@b.com")]

    def test_per_category_metrics(self) -> None:
        samples = [
            {
                "id": "s1",
                "text": "...",
                "expected": [
                    {"category": "email", "value": "a@b.com"},
                    {"category": "phone_kr", "value": "010-1234-5678"},
                ],
            }
        ]
        with patch("synapse_memory.eval.golden.redact_full") as mock_rf:
            mock_rf.return_value = RedactionResult(
                redacted="...",
                detections=[
                    _detection("email", "a@b.com"),
                    _detection("phone_kr", "010-1234-5678"),
                ],
            )
            result = evaluate(samples, env=_ready_env())

        assert result.per_category["email"].tp == 1
        assert result.per_category["phone_kr"].tp == 1

    def test_progress_callback(self) -> None:
        samples = [
            {"id": f"s{i}", "text": "x", "expected": []} for i in range(3)
        ]
        calls: list[tuple[int, int]] = []
        with patch("synapse_memory.eval.golden.redact_full") as mock_rf:
            mock_rf.return_value = RedactionResult(redacted="...", detections=[])
            evaluate(
                samples,
                env=_ready_env(),
                on_progress=lambda i, t: calls.append((i, t)),
            )
        assert calls == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------------------
# default path
# ---------------------------------------------------------------------------


def test_default_synthetic_path_exists() -> None:
    """패키지에 동봉된 합성 골든셋이 실재."""
    p = default_synthetic_path()
    assert p.exists(), f"기본 골든셋 없음: {p}"


def test_default_synthetic_set_loadable() -> None:
    """JSON 형식 자체 검증 — 모든 sample에 id/text/expected 존재."""
    samples = load_golden_set(default_synthetic_path())
    assert len(samples) >= 30
    for s in samples:
        assert "id" in s
        assert "text" in s
        assert isinstance(s.get("expected", []), list)
