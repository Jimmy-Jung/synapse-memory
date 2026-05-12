"""Feedback CLI tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import synapse_memory.cli as cli_mod
from synapse_memory.cards.project import ProjectCard, save_project_card
from synapse_memory.cli import cmd_feedback
from synapse_memory.storage.l0 import L0_ENV_VAR
from synapse_memory.storage.last_response import (
    AnswerCitation,
    LastAnswerReference,
    save_last_answer,
)


def _last_args(**overrides: object) -> argparse.Namespace:
    data = {
        "feedback_target": "last",
        "target_ref": None,
        "accept": False,
        "reject": "관련 없음",
        "weight": None,
        "vault_path": None,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def _target_args(target: str, target_ref: str, **overrides: object) -> argparse.Namespace:
    data = {
        "feedback_target": target,
        "target_ref": target_ref,
        "accept": False,
        "reject": "관련 없음",
        "weight": None,
        "vault_path": None,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def _save_last() -> None:
    save_last_answer(
        LastAnswerReference(
            answer_id="answer-1",
            ts="2026-05-12T00:00:00.000000Z",
            command="ask",
            query="q",
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
    )


def test_feedback_last_reject_records_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    _save_last()

    rc = cmd_feedback(_last_args())

    assert rc == 0
    assert "Recorded reject" in capsys.readouterr().out
    assert "dansim-ios" in (tmp_path / "private" / "feedback.jsonl").read_text(
        encoding="utf-8"
    )


def test_feedback_last_without_context_noops(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))

    rc = cmd_feedback(_last_args())

    assert rc == 1
    assert "No recent answer" in capsys.readouterr().err
    assert not (tmp_path / "private" / "feedback.jsonl").exists()


def test_feedback_reject_requires_reason(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_feedback(_last_args(reject=" "))

    assert rc == 1
    assert "reason" in capsys.readouterr().err


def test_parser_has_feedback_command() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["feedback", "last", "--accept"])

    assert args.func is cmd_feedback
    assert args.feedback_target == "last"


def test_feedback_card_records_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    save_project_card(
        ProjectCard(project_id="dansim-ios", display_name="단심"),
        vault_path=tmp_path,
    )

    rc = cmd_feedback(
        _target_args("card", "dansim-ios", accept=True, reject=None, vault_path=str(tmp_path))
    )

    assert rc == 0
    assert "Recorded accept" in capsys.readouterr().out
    assert "dansim-ios" in (tmp_path / "private" / "feedback.jsonl").read_text(
        encoding="utf-8"
    )


def test_feedback_pattern_records_weight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
    ai_dir = tmp_path / "90_System" / "AI"
    ai_dir.mkdir(parents=True)
    (ai_dir / "DecisionPatterns.md").write_text(
        "- trigger: 큰 작업 시작\n"
        "  action: 계획 먼저 작성\n",
        encoding="utf-8",
    )

    rc = cmd_feedback(
        _target_args(
            "pattern",
            "pattern-b330dfadf791",
            reject=None,
            weight=-0.3,
            vault_path=str(tmp_path),
        )
    )

    assert rc == 0
    assert "pattern-b330dfadf791" in (
        tmp_path / "private" / "feedback.jsonl"
    ).read_text(encoding="utf-8")
