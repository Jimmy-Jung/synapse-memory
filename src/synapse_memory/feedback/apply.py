"""Apply feedback events to ranking signals."""

from __future__ import annotations

from dataclasses import dataclass

from synapse_memory.feedback.events import FeedbackEvent

MIN_FEEDBACK_SCORE = 0.5
MAX_FEEDBACK_SCORE = 1.5
DEFAULT_FEEDBACK_SCORE = 1.0


@dataclass(frozen=True)
class FeedbackAggregate:
    target_kind: str
    target_ref: str
    score: float
    events_count: int
    last_event_ts: str | None = None


def card_feedback_scores(
    events: list[FeedbackEvent],
) -> dict[str, FeedbackAggregate]:
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    last_ts: dict[str, str] = {}
    for event in sorted(events, key=lambda e: e.ts):
        if event.target_kind != "card":
            continue
        current = scores.get(event.target_ref, DEFAULT_FEEDBACK_SCORE)
        scores[event.target_ref] = _clamp(current * _multiplier(event))
        counts[event.target_ref] = counts.get(event.target_ref, 0) + 1
        last_ts[event.target_ref] = event.ts
    return {
        target_ref: FeedbackAggregate(
            target_kind="card",
            target_ref=target_ref,
            score=round(score, 4),
            events_count=counts[target_ref],
            last_event_ts=last_ts.get(target_ref),
        )
        for target_ref, score in scores.items()
    }


def _multiplier(event: FeedbackEvent) -> float:
    if event.action == "reject":
        return 0.85
    if event.action == "accept":
        return 1.10
    return 1.0 + event.weight


def _clamp(value: float) -> float:
    return min(MAX_FEEDBACK_SCORE, max(MIN_FEEDBACK_SCORE, value))
