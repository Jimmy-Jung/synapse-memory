"""Feedback event storage tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from synapse_memory.feedback.events import (
    FeedbackAction,
    FeedbackEvent,
    append_feedback_event,
    build_feedback_event,
    load_feedback_events,
)
from synapse_memory.storage.l0 import L0_ENV_VAR, L0_FILE_MODE


def test_build_reject_requires_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        build_feedback_event(
            target_kind="card",
            target_ref="dansim-ios",
            action="reject",
            reason=" ",
        )


def test_build_reject_masks_reason() -> None:
    event = build_feedback_event(
        target_kind="card",
        target_ref="dansim-ios",
        action="reject",
        reason="전화번호 010-1234-5678 관련 없음",
    )

    assert "010-1234-5678" not in (event.reason or "")
    assert event.weight == -0.3
    assert event.action == "reject"


def test_build_accept_defaults_weight() -> None:
    event = build_feedback_event(
        target_kind="card",
        target_ref="dansim-ios",
        action="accept",
    )

    assert event.weight == 0.2


@pytest.mark.parametrize("action", ["accept", "reject", "weight"])
def test_action_type(action: FeedbackAction) -> None:
    event = build_feedback_event(
        target_kind="card",
        target_ref="x",
        action=action,
        reason="r" if action == "reject" else None,
        weight=0.1 if action == "weight" else None,
    )

    assert event.action == action


def test_weight_range_validation() -> None:
    with pytest.raises(ValueError, match="weight"):
        build_feedback_event(
            target_kind="card",
            target_ref="x",
            action="weight",
            weight=1.5,
        )


def test_append_and_load_feedback_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    event = build_feedback_event(
        target_kind="card",
        target_ref="dansim-ios",
        action="accept",
    )

    path = append_feedback_event(event)
    loaded = load_feedback_events()

    assert path.name == "feedback.jsonl"
    assert stat.S_IMODE(path.stat().st_mode) == L0_FILE_MODE
    assert loaded == [event]


def test_load_recovers_corrupt_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    good = build_feedback_event(
        target_kind="card",
        target_ref="dansim-ios",
        action="accept",
    )
    path = append_feedback_event(good)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{bad json\n")
        fh.write(json.dumps({"event_id": "lost"}) + "\n")

    loaded = load_feedback_events(recover=True)
    backups = list(path.parent.glob("feedback.jsonl.bak.*"))

    assert loaded == [good]
    assert backups
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_feedback_event_round_trip() -> None:
    event = FeedbackEvent(
        event_id="20260512T000000000000Z-a1b2c3d4",
        ts="2026-05-12T00:00:00.000000Z",
        target_kind="answer",
        target_ref="answer-1",
        action="reject",
        weight=-0.3,
        reason="관련 없음",
        answer_id_context=None,
    )

    assert FeedbackEvent.from_dict(event.to_dict()) == event
