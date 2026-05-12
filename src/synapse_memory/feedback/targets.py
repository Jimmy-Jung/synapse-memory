"""Feedback target resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synapse_memory.cards.company import load_company_card
from synapse_memory.cards.project import load_project_card
from synapse_memory.profile.patterns import find_decision_pattern
from synapse_memory.storage.last_response import LastAnswerReference


@dataclass(frozen=True)
class FeedbackTarget:
    target_kind: str
    target_ref: str
    display_name: str


def resolve_last_answer_targets(ref: LastAnswerReference) -> list[FeedbackTarget]:
    if not ref.citations:
        raise ValueError("last answer has no citation targets")
    return [
        FeedbackTarget(
            target_kind=c.target_kind,
            target_ref=c.target_ref,
            display_name=c.display_name or c.target_ref,
        )
        for c in ref.citations
    ]


def resolve_card_target(card_id: str, *, vault_path: Path | None = None) -> FeedbackTarget:
    try:
        project = load_project_card(card_id, vault_path=vault_path)
        return FeedbackTarget(
            target_kind="card",
            target_ref=project.project_id,
            display_name=project.display_name,
        )
    except FileNotFoundError:
        pass

    try:
        company = load_company_card(card_id, vault_path=vault_path)
        return FeedbackTarget(
            target_kind="card",
            target_ref=company.company_id,
            display_name=company.display_name,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"Card target not found: {card_id}") from exc


def resolve_pattern_target(
    pattern_id: str, *, vault_path: Path | None = None
) -> FeedbackTarget:
    pattern = find_decision_pattern(pattern_id, vault_path=vault_path)
    if pattern is None:
        raise ValueError(f"DecisionPattern target not found: {pattern_id}")
    return FeedbackTarget(
        target_kind="pattern",
        target_ref=pattern.pattern_id,
        display_name=pattern.display_name,
    )
