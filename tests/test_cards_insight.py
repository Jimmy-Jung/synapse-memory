"""Insight Card 모듈 테스트.

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from synapse_memory.cards.insight import (
    DEFAULT_INSIGHTS_SUBPATH,
    InsightCard,
    insights_dir,
    list_insight_cards,
    load_insight_card,
    new_insight_id,
    parse_insight_card,
    save_insight_card,
    serialize_insight_card,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


def test_new_insight_id_has_date_prefix_and_slug() -> None:
    insight_id = new_insight_id(
        "TCA를 왜 도입했지?",
        now=datetime(2026, 6, 11, 14, 32),
    )

    assert insight_id == "2026-06-11-tca를-왜-도입했지"


def test_serialize_parse_round_trip() -> None:
    card = InsightCard(
        insight_id="2026-06-11-tca",
        question="TCA를 왜 도입했지?",
        command="ask",
        created="2026-06-11T14:32:00+09:00",
        related=["dansim-ios", "webview-refactor"],
        keywords=["TCA", "아키텍처"],
        body="답변 본문 [dansim-ios].",
    )

    text = serialize_insight_card(card)
    parsed = parse_insight_card(text)

    assert parsed.insight_id == card.insight_id
    assert parsed.question == card.question
    assert parsed.related == ["dansim-ios", "webview-refactor"]
    assert "답변 본문" in parsed.body


def test_save_and_load_uses_year_month_path(vault: Path) -> None:
    card = InsightCard(
        insight_id="2026-06-11-tca",
        question="TCA?",
        command="ask",
        created="2026-06-11T14:32:00+09:00",
        body="본문",
    )

    path = save_insight_card(card, vault_path=vault)

    assert path.relative_to(vault) == DEFAULT_INSIGHTS_SUBPATH / "2026" / "06" / "2026-06-11-tca.md"
    assert insights_dir(card.created, vault_path=vault).relative_to(vault) == DEFAULT_INSIGHTS_SUBPATH / "2026" / "06"
    assert load_insight_card(card.insight_id, card.created, vault_path=vault).body == "본문"


def test_save_does_not_overwrite_existing_insight(vault: Path) -> None:
    first = InsightCard(
        insight_id="2026-06-11-tca",
        question="TCA?",
        command="ask",
        created="2026-06-11T14:32:00+09:00",
        body="첫 번째",
    )
    second = InsightCard(
        insight_id="2026-06-11-tca",
        question="TCA?",
        command="ask",
        created="2026-06-11T14:33:00+09:00",
        body="두 번째",
    )

    first_path = save_insight_card(first, vault_path=vault)
    second_path = save_insight_card(second, vault_path=vault)

    assert first_path.name == "2026-06-11-tca.md"
    assert second_path.name == "2026-06-11-tca-2.md"
    assert second.insight_id == "2026-06-11-tca-2"
    assert "첫 번째" in first_path.read_text(encoding="utf-8")
    assert "두 번째" in second_path.read_text(encoding="utf-8")


def test_list_insight_cards_recurses_year_month_and_skips_invalid(vault: Path) -> None:
    save_insight_card(
        InsightCard(
            insight_id="2026-06-11-a",
            question="A",
            command="ask",
            created="2026-06-11T10:00:00+09:00",
        ),
        vault_path=vault,
    )
    save_insight_card(
        InsightCard(
            insight_id="2026-07-01-b",
            question="B",
            command="ask",
            created="2026-07-01T10:00:00+09:00",
        ),
        vault_path=vault,
    )
    broken = vault / DEFAULT_INSIGHTS_SUBPATH / "2026" / "07" / "broken.md"
    broken.write_text("frontmatter 없음", encoding="utf-8")

    cards = list_insight_cards(vault_path=vault)

    assert [card.insight_id for card in cards] == [
        "2026-06-11-a",
        "2026-07-01-b",
    ]
