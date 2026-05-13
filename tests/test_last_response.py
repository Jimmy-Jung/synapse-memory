"""Last answer reference storage tests.

저자: Synapse Memory Maintainers
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


# Legacy command 자동 마이그레이션 (M1a → persona deep rename)
# -----------------------------------------------------------------


def test_load_legacy_me_command_migrates_to_persona(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pre-rename 시점에 저장된 me.* command 식별자가 load 시 persona.* 로 자동 변환."""
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))

    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    legacy_payload = {
        "answer_id": "20260513T000000000000Z-legacy01",
        "ts": "2026-05-13T00:00:00.000000Z",
        "command": "me.generate.decide",
        "query": "이전 호출 (M1a 이전)",
        "session_id": None,
        "citations": [],
    }
    (private / "last_response.json").write_text(
        json.dumps(legacy_payload), encoding="utf-8"
    )

    ref = load_last_answer()
    assert ref is not None
    assert ref.command == "persona.generate.decide"


def test_load_legacy_me_what_did_i_think_migrates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    payload = {
        "answer_id": "20260513T000000000000Z-legacy02",
        "ts": "2026-05-13T00:00:00.000000Z",
        "command": "me.what_did_i_think",
        "query": "주제",
        "session_id": None,
        "citations": [],
    }
    (private / "last_response.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    ref = load_last_answer()
    assert ref is not None
    assert ref.command == "persona.what_did_i_think"


def test_load_already_persona_command_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """이미 persona.* 형식이면 그대로 유지."""
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    payload = {
        "answer_id": "20260513T000000000000Z-current",
        "ts": "2026-05-13T00:00:00.000000Z",
        "command": "persona.generate.resume",
        "query": "회사X",
        "session_id": None,
        "citations": [],
    }
    (private / "last_response.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    ref = load_last_answer()
    assert ref is not None
    assert ref.command == "persona.generate.resume"


def test_load_unrelated_command_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """me. prefix 가 아닌 식별자 (예: ask) 는 변환되지 않음."""
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    payload = {
        "answer_id": "20260513T000000000000Z-ask01",
        "ts": "2026-05-13T00:00:00.000000Z",
        "command": "ask",
        "query": "질의",
        "session_id": None,
        "citations": [],
    }
    (private / "last_response.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    ref = load_last_answer()
    assert ref is not None
    assert ref.command == "ask"
