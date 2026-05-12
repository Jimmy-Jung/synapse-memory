"""Last answer reference storage tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from synapse_memory.storage.l0 import L0_ENV_VAR, L0_FILE_MODE
from synapse_memory.storage.last_response import (
    AnswerCitation,
    LastAnswerReference,
    load_last_answer,
    save_last_answer,
)


def _ref() -> LastAnswerReference:
    return LastAnswerReference(
        answer_id="20260512T000000000000Z-a1b2c3d4",
        ts="2026-05-12T00:00:00.000000Z",
        command="ask",
        query="질문",
        citations=(
            AnswerCitation(
                target_kind="card",
                target_ref="dansim-ios",
                source_kind="card_project",
                display_name="단심",
            ),
        ),
        session_id=None,
    )


def test_save_load_last_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    path = save_last_answer(_ref())

    assert stat.S_IMODE(path.stat().st_mode) == L0_FILE_MODE
    assert load_last_answer() == _ref()


def test_last_answer_does_not_store_answer_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    path = save_last_answer(_ref())
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "answer" not in data
    assert "answer_text" not in data


def test_missing_last_answer_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))

    assert load_last_answer() is None
