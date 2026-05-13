"""Feedback aggregation tests.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from synapse_memory.feedback.apply import card_feedback_scores
from synapse_memory.feedback.events import FeedbackEvent


def _event(target_ref: str, action: str, weight: float) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=f"event-{target_ref}-{action}-{weight}",
        ts="2026-05-12T00:00:00.000000Z",
        target_kind="card",
        target_ref=target_ref,
        action=action,  # type: ignore[arg-type]
        weight=weight,
        reason=None,
        answer_id_context=None,
    )


def test_reject_lowers_card_score() -> None:
    scores = card_feedback_scores([_event("dansim-ios", "reject", -0.3)])

    assert scores["dansim-ios"].score == 0.85


def test_accept_raises_card_score() -> None:
    scores = card_feedback_scores([_event("dansim-ios", "accept", 0.2)])

    assert scores["dansim-ios"].score == 1.1


def test_score_is_clamped() -> None:
    events = [_event("x", "accept", 0.2) for _ in range(20)]

    assert card_feedback_scores(events)["x"].score == 1.5
