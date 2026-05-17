"""Tests for node/* frontmatter tags (US1 of 015-graph-viz)."""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from synapse_memory.cards.company import CompanyCard, serialize_company_card
from synapse_memory.cards.project import ProjectCard, serialize_project_card
from synapse_memory.daily import DailyResult, write_daily_report
from synapse_memory.profile.extract import ProfileFact, save_profile_update


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---"), "frontmatter 필요"
    yaml_text = text.split("---", 2)[1]
    return yaml.safe_load(yaml_text) or {}


def test_project_card_has_node_card_tag() -> None:
    card = ProjectCard(project_id="proj-x", display_name="Project X")
    text = serialize_project_card(card)
    fm = _parse_frontmatter(text)
    tags = fm.get("tags", [])
    assert "node/card" in tags


def test_company_card_has_node_card_tag() -> None:
    card = CompanyCard(company_id="acme", display_name="Acme")
    text = serialize_company_card(card)
    fm = _parse_frontmatter(text)
    tags = fm.get("tags", [])
    assert "node/card" in tags


def test_profile_update_has_node_profile_update_tag(tmp_path: Path) -> None:
    fact = ProfileFact(
        category="tech",
        statement="iOS 개발",
        confidence=0.9,
        extracted_at="2026-05-17",
    )
    path = save_profile_update(
        [fact], None, vault_path=tmp_path, date=datetime.date(2026, 5, 17)
    )
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tags = fm.get("tags", [])
    assert "node/profile-update" in tags


def test_daily_report_has_node_daily_report_tag(tmp_path: Path) -> None:
    result = DailyResult()
    path = write_daily_report(
        result, date=datetime.date(2026, 5, 17), vault_path=tmp_path
    )
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tags = fm.get("tags", [])
    assert "node/daily-report" in tags
