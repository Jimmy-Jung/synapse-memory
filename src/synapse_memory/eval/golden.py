"""골든셋 기반 PII redaction 정확도 측정.

각 sample::

    {"id": "...", "text": "...", "expected": [{"category": ..., "value": ...}, ...]}

매칭은 ``(category, value)`` 튜플 기준 — 같은 값이 여러번 나오면 multi-set로 셈.

산출 metric:
    - per-category: TP/FP/FN, precision, recall, F1
    - overall: 전체 합산
    - failures: FP/FN이 발생한 sample 목록 (튜닝 단서)

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from synapse_memory.llm.apfel import ApfelEnvironment, detect_environment
from synapse_memory.redaction import redact_full


class GoldenSample(TypedDict, total=False):
    """골든셋 sample 형식."""

    id: str
    text: str
    expected: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class CategoryMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class SampleFailure:
    sample_id: str
    text: str
    fp: list[tuple[str, str]] = field(default_factory=list)
    fn: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class GoldenResult:
    per_category: dict[str, CategoryMetrics] = field(default_factory=dict)
    overall: CategoryMetrics = field(default_factory=CategoryMetrics)
    failures: list[SampleFailure] = field(default_factory=list)
    samples_total: int = 0
    samples_perfect: int = 0  # FP+FN==0인 sample 수


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_golden_set(path: Path) -> list[GoldenSample]:
    """JSON 파일 로드 → samples 리스트.

    구조::

        {"samples": [{"id", "text", "expected": [...]}, ...]}
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    samples = raw.get("samples")
    if not isinstance(samples, list):
        raise ValueError(f"{path}: 'samples' 키가 list 아님")
    return samples


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def _to_multiset(items: Iterable[tuple[str, str]]) -> Counter[tuple[str, str]]:
    """(cat, value) 튜플을 multi-set으로 변환 (중복 보존)."""
    return Counter(items)


def _diff_multisets(
    detected: Counter[tuple[str, str]],
    expected: Counter[tuple[str, str]],
) -> tuple[
    Counter[tuple[str, str]],
    Counter[tuple[str, str]],
    Counter[tuple[str, str]],
]:
    """multi-set 비교 → (TP, FP, FN) Counter. 0 count entry는 포함하지 않음."""
    tp: Counter[tuple[str, str]] = Counter()
    fp: Counter[tuple[str, str]] = Counter()
    fn: Counter[tuple[str, str]] = Counter()

    all_keys = set(detected) | set(expected)
    for key in all_keys:
        d_count = detected[key]
        e_count = expected[key]
        common = min(d_count, e_count)
        if common > 0:
            tp[key] = common
        if d_count > e_count:
            fp[key] = d_count - e_count
        elif e_count > d_count:
            fn[key] = e_count - d_count
    return tp, fp, fn


def _collect_categories_from_counters(
    *counters: Counter[tuple[str, str]],
) -> set[str]:
    return {c for ctr in counters for c, _ in ctr}


def evaluate(
    samples: list[GoldenSample],
    *,
    env: ApfelEnvironment | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> GoldenResult:
    """골든셋 전체 평가 → GoldenResult.

    Args:
        samples: ``load_golden_set`` 결과.
        env: apfel 환경 (사전 진단 재사용 권장).
        on_progress: ``(current, total)`` 콜백 — CLI 진행 표시용.
    """
    env = env or detect_environment()
    result = GoldenResult(samples_total=len(samples))

    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, len(samples))

        text = sample["text"]
        expected_pairs = [
            (e["category"], e["value"]) for e in sample.get("expected", [])
        ]

        redaction = redact_full(text, env=env)
        detected_pairs = [(d.category, d.matched) for d in redaction.detections]

        det_ms = _to_multiset(detected_pairs)
        exp_ms = _to_multiset(expected_pairs)
        tp_ms, fp_ms, fn_ms = _diff_multisets(det_ms, exp_ms)

        # 카테고리별 합산
        for cat in _collect_categories_from_counters(tp_ms, fp_ms, fn_ms):
            cm = result.per_category.setdefault(cat, CategoryMetrics())
            cm.tp += sum(v for k, v in tp_ms.items() if k[0] == cat)
            cm.fp += sum(v for k, v in fp_ms.items() if k[0] == cat)
            cm.fn += sum(v for k, v in fn_ms.items() if k[0] == cat)

        result.overall.tp += sum(tp_ms.values())
        result.overall.fp += sum(fp_ms.values())
        result.overall.fn += sum(fn_ms.values())

        if not fp_ms and not fn_ms:
            result.samples_perfect += 1
        else:
            result.failures.append(
                SampleFailure(
                    sample_id=str(sample.get("id", f"#{i}")),
                    text=text[:120],
                    fp=sorted(fp_ms.elements()),
                    fn=sorted(fn_ms.elements()),
                )
            )

    return result


# ---------------------------------------------------------------------------
# 기본 골든셋 위치
# ---------------------------------------------------------------------------


def default_synthetic_path() -> Path:
    """패키지에 동봉된 합성 골든셋 경로.

    개발용 — production 패키지 빌드 시엔 별도 packaging 고려.
    """
    here = Path(__file__).resolve().parent
    # repo 루트 / tests/golden/pii_synthetic.json
    candidate = here.parent.parent.parent / "tests" / "golden" / "pii_synthetic.json"
    return candidate
