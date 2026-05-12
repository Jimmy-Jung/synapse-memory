"""Feedback target resolution tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.cards.company import CompanyCard, save_company_card
from synapse_memory.cards.project import ProjectCard, save_project_card
from synapse_memory.feedback.targets import (
    FeedbackTarget,
    resolve_card_target,
    resolve_last_answer_targets,
    resolve_pattern_target,
)
from synapse_memory.storage.last_response import (
    AnswerCitation,
    LastAnswerReference,
)


def test_resolve_last_answer_targets_from_citations() -> None:
    ref = LastAnswerReference(
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

    targets = resolve_last_answer_targets(ref)

    assert targets == [
        FeedbackTarget(
            target_kind="card",
            target_ref="dansim-ios",
            display_name="단심",
        )
    ]


def test_resolve_last_answer_requires_citations() -> None:
    ref = LastAnswerReference(
        answer_id="answer-1",
        ts="2026-05-12T00:00:00.000000Z",
        command="ask",
        query="q",
        citations=(),
        session_id=None,
    )

    with pytest.raises(ValueError, match="citation"):
        resolve_last_answer_targets(ref)


def test_resolve_project_card_target(tmp_path: Path) -> None:
    save_project_card(
        ProjectCard(project_id="dansim-ios", display_name="단심"),
        vault_path=tmp_path,
    )

    target = resolve_card_target("dansim-ios", vault_path=tmp_path)

    assert target.target_kind == "card"
    assert target.display_name == "단심"


def test_resolve_company_card_target(tmp_path: Path) -> None:
    save_company_card(
        CompanyCard(company_id="danggeun", display_name="당근마켓"),
        vault_path=tmp_path,
    )

    target = resolve_card_target("danggeun", vault_path=tmp_path)

    assert target.target_ref == "danggeun"
    assert target.display_name == "당근마켓"


def test_resolve_unknown_card_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Card"):
        resolve_card_target("missing", vault_path=tmp_path)


def test_resolve_pattern_target(tmp_path: Path) -> None:
    ai_dir = tmp_path / "90_System" / "AI"
    ai_dir.mkdir(parents=True)
    (ai_dir / "DecisionPatterns.md").write_text(
        "- trigger: 큰 작업 시작\n"
        "  action: 계획 먼저 작성\n"
        "  rationale: 범위 관리\n",
        encoding="utf-8",
    )

    target = resolve_pattern_target(
        "pattern-b330dfadf791",
        vault_path=tmp_path,
    )

    assert target.target_kind == "pattern"
    assert target.display_name == "큰 작업 시작 -> 계획 먼저 작성"
