"""Pass 1 — deterministic regex/validator 기반 redaction.

흐름:
    text → 모든 패턴 매치 수집 → priority 내림차순 정렬 → 겹침 제거 →
    같은 (category, value)에 같은 인덱스 부여 → right-to-left 치환

핵심:
- placeholder는 stable: 같은 값이 여러번 나오면 같은 ``[PHONE_1]``.
- validator(Luhn, RRN 체크섬, IPv4 옥텟)로 false-positive 컷.
- 우선순위 높은 패턴이 짧은 패턴을 덮음 (JWT 안에 IP 패턴이 있어도 JWT로 묶임).

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from synapse_memory.redaction.patterns import DEFAULT_PATTERNS, Pattern


@dataclass(frozen=True)
class Detection:
    """단일 PII 검출 결과.

    matched 필드는 원본 값을 보존 (감사·재현용). 외부에 노출하지 말 것.
    placeholder는 redacted 텍스트에 들어가는 마스크.
    """

    category: str
    span: tuple[int, int]
    matched: str
    placeholder: str


@dataclass
class RedactionResult:
    """Pass 1 결과."""

    redacted: str
    detections: list[Detection] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return len(self.detections) > 0

    def category_counts(self) -> dict[str, int]:
        """카테고리별 검출 수. 통계/감사용."""
        counts: dict[str, int] = {}
        for d in self.detections:
            counts[d.category] = counts.get(d.category, 0) + 1
        return counts


def _collect_matches(
    text: str, patterns: Sequence[Pattern]
) -> list[tuple[int, int, Pattern, str]]:
    """priority 내림차순으로 매치 수집. 이미 점유된 span과 겹치면 skip.

    Returns:
        (start, end, pattern, matched_str) 리스트 — 텍스트 내 위치 오름차순.
    """
    occupied: list[tuple[int, int]] = []
    raw: list[tuple[int, int, Pattern, str]] = []

    sorted_patterns = sorted(patterns, key=lambda p: -p.priority)

    for pattern in sorted_patterns:
        for m in pattern.regex.finditer(text):
            start, end = m.span()
            matched = m.group()

            # validator 통과 못하면 skip
            if pattern.validator is not None and not pattern.validator(matched):
                continue

            # 이미 더 높은 priority가 점유한 영역과 겹치면 skip
            if any(s < end and e > start for s, e in occupied):
                continue

            occupied.append((start, end))
            raw.append((start, end, pattern, matched))

    raw.sort(key=lambda t: t[0])
    return raw


def _assign_stable_indices(
    raw: list[tuple[int, int, Pattern, str]],
) -> list[Detection]:
    """같은 (category, matched value)에 같은 인덱스 부여."""
    counters: dict[str, dict[str, int]] = {}
    detections: list[Detection] = []

    for start, end, pattern, matched in raw:
        per_cat = counters.setdefault(pattern.name, {})
        if matched not in per_cat:
            per_cat[matched] = len(per_cat) + 1
        idx = per_cat[matched]
        detections.append(
            Detection(
                category=pattern.name,
                span=(start, end),
                matched=matched,
                placeholder=pattern.make_placeholder(idx),
            )
        )
    return detections


def _apply_replacements(text: str, detections: list[Detection]) -> str:
    """right-to-left 치환 — 인덱스가 깨지지 않도록."""
    chars = list(text)
    for det in sorted(detections, key=lambda d: -d.span[0]):
        s, e = det.span
        chars[s:e] = list(det.placeholder)
    return "".join(chars)


def redact(
    text: str,
    *,
    patterns: Sequence[Pattern] = DEFAULT_PATTERNS,
) -> RedactionResult:
    """Pass 1 redaction.

    Args:
        text: 검사 대상.
        patterns: 사용할 패턴 셋. 기본 ``DEFAULT_PATTERNS``.

    Returns:
        RedactionResult — redacted 텍스트 + 검출 리스트 (원본 span 기준).
    """
    if not text:
        return RedactionResult(redacted=text)

    raw = _collect_matches(text, patterns)
    detections = _assign_stable_indices(raw)
    redacted = _apply_replacements(text, detections)

    return RedactionResult(redacted=redacted, detections=detections)
