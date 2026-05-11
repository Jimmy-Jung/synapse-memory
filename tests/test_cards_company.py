"""Company Card 테스트.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.cards.company import (
    DEFAULT_COMPANIES_SUBPATH,
    CompanyCard,
    JobPosition,
    list_company_cards,
    load_company_card,
    parse_company_card,
    save_company_card,
    serialize_company_card,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


class TestRoundTrip:
    def test_minimal(self) -> None:
        card = CompanyCard(
            company_id="danggeun",
            display_name="당근마켓",
            body="## 회사 개요\n중고 거래",
        )
        text = serialize_company_card(card)
        parsed = parse_company_card(text)
        assert parsed.company_id == "danggeun"
        assert parsed.display_name == "당근마켓"
        assert "중고 거래" in parsed.body

    def test_full(self) -> None:
        card = CompanyCard(
            company_id="danggeun",
            display_name="당근마켓",
            status="applied",
            country="KR",
            size="medium",
            website="https://www.daangn.com",
            positions=[
                JobPosition(
                    title="Senior iOS Engineer",
                    seniority="senior",
                    keywords=["Swift", "mobile"],
                    jd_url="https://daangn.com/jobs/123",
                )
            ],
            notes="레퍼럴 가능",
            confidence=0.9,
            created="2026-05-10",
        )
        parsed = parse_company_card(serialize_company_card(card))
        assert parsed.country == "KR"
        assert parsed.size == "medium"
        assert len(parsed.positions) == 1
        assert parsed.positions[0].keywords == ["Swift", "mobile"]
        assert parsed.confidence == 0.9


class TestParsing:
    def test_no_frontmatter_raises(self) -> None:
        with pytest.raises(ValueError, match="frontmatter"):
            parse_company_card("# 본문")

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValueError, match="필수 필드 누락"):
            parse_company_card("---\nstatus: target\n---\n본문")


class TestDiskIO:
    def test_save_load(self, vault: Path) -> None:
        card = CompanyCard(company_id="x", display_name="X Corp")
        path = save_company_card(card, vault_path=vault)
        assert path.relative_to(vault) == DEFAULT_COMPANIES_SUBPATH / "x.md"
        loaded = load_company_card("x", vault_path=vault)
        assert loaded.display_name == "X Corp"

    def test_list_sorted(self, vault: Path) -> None:
        for cid in ["zeta", "alpha", "delta"]:
            save_company_card(
                CompanyCard(company_id=cid, display_name=cid),
                vault_path=vault,
            )
        cards = list_company_cards(vault_path=vault)
        assert [c.company_id for c in cards] == ["alpha", "delta", "zeta"]

    def test_list_empty(self, vault: Path) -> None:
        assert list_company_cards(vault_path=vault) == []
