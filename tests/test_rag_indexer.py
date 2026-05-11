"""indexer.py 테스트 — embeddings/vector store 모두 mock.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse_memory.cards.company import (
    CompanyCard,
    JobPosition,
    save_company_card,
)
from synapse_memory.cards.project import (
    ProjectCard,
    ProjectMetric,
    save_project_card,
)
from synapse_memory.rag.indexer import (
    PREFIX_COMPANY,
    PREFIX_PROJECT,
    company_card_to_text,
    index_cards,
    project_card_to_text,
)
from synapse_memory.rag.vector_store import VectorStore


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


# ---------------------------------------------------------------------------
# 텍스트 변환
# ---------------------------------------------------------------------------


class TestProjectCardToText:
    def test_includes_key_fields(self) -> None:
        card = ProjectCard(
            project_id="dansim",
            display_name="단심 (명상 앱)",
            role="iOS Lead",
            period_start="2023-09",
            period_end="2024-12",
            domains=["ios", "mobile"],
            stack=["Swift", "TCA"],
            keywords=["retention"],
            metrics=[
                ProjectMetric(name="D7 retention", before="18%", after="31%"),
            ],
            body="## 문제\n복잡한 본문",
        )
        text = project_card_to_text(card)
        assert "단심" in text
        assert "iOS Lead" in text
        assert "Swift" in text
        assert "TCA" in text
        assert "retention" in text
        assert "18% → 31%" in text
        assert "복잡한 본문" in text

    def test_minimal_card(self) -> None:
        card = ProjectCard(project_id="x", display_name="X")
        text = project_card_to_text(card)
        assert "# X" in text

    def test_metric_value_only(self) -> None:
        card = ProjectCard(
            project_id="x",
            display_name="X",
            metrics=[ProjectMetric(name="DAU", value="10K")],
        )
        text = project_card_to_text(card)
        assert "DAU: 10K" in text


class TestCompanyCardToText:
    def test_includes_positions(self) -> None:
        card = CompanyCard(
            company_id="danggeun",
            display_name="당근마켓",
            country="KR",
            size="medium",
            positions=[
                JobPosition(
                    title="Senior iOS",
                    seniority="senior",
                    keywords=["Swift", "mobile"],
                )
            ],
            body="## 회사 개요\n중고거래",
        )
        text = company_card_to_text(card)
        assert "당근마켓" in text
        assert "KR" in text
        assert "Senior iOS" in text
        assert "Swift" in text
        assert "중고거래" in text


# ---------------------------------------------------------------------------
# index_cards (mock)
# ---------------------------------------------------------------------------


class TestIndexCards:
    def _setup_vault(self, vault: Path) -> None:
        save_project_card(
            ProjectCard(
                project_id="dansim",
                display_name="단심",
                role="iOS Lead",
                domains=["ios"],
                stack=["Swift"],
                body="## 문제\n낮은 retention",
            ),
            vault_path=vault,
        )
        save_company_card(
            CompanyCard(
                company_id="danggeun",
                display_name="당근마켓",
                country="KR",
                body="## 개요\n중고거래",
            ),
            vault_path=vault,
        )

    def _fake_store(self) -> MagicMock:
        store = MagicMock(spec=VectorStore)
        store.upsert.return_value = 0
        store.clear.return_value = None
        return store

    def test_indexes_both_kinds(self, vault: Path) -> None:
        self._setup_vault(vault)
        store = self._fake_store()
        # bge-m3 응답 mock
        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            return_value=[[0.1] * 1024, [0.2] * 1024],
        ):
            stats = index_cards(store=store, vault_path=vault)

        assert stats.project_cards == 1
        assert stats.company_cards == 1
        assert stats.bytes_indexed > 0

        # 두 번 upsert (project 1번, company 1번)
        assert store.upsert.call_count == 2

    def test_rebuild_clears_first(self, vault: Path) -> None:
        self._setup_vault(vault)
        store = self._fake_store()
        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            return_value=[[0.1] * 1024],
        ):
            index_cards(store=store, vault_path=vault, rebuild=True)
        store.clear.assert_called_once()

    def test_empty_vault(self, vault: Path) -> None:
        store = self._fake_store()
        with patch("synapse_memory.rag.indexer.embed_texts", return_value=[]):
            stats = index_cards(store=store, vault_path=vault)
        assert stats.total_cards == 0
        store.upsert.assert_not_called()

    def test_id_prefixes(self, vault: Path) -> None:
        self._setup_vault(vault)
        store = self._fake_store()
        upserted_ids: list[str] = []

        def _capture(records):
            for r in records:
                upserted_ids.append(r.id)

        store.upsert.side_effect = _capture
        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            return_value=[[0.1] * 1024, [0.2] * 1024],
        ):
            index_cards(store=store, vault_path=vault)

        assert any(i.startswith(PREFIX_PROJECT) for i in upserted_ids)
        assert any(i.startswith(PREFIX_COMPANY) for i in upserted_ids)

    def test_metadata_includes_source_kind(self, vault: Path) -> None:
        self._setup_vault(vault)
        store = self._fake_store()
        captured: list = []

        def _capture(records):
            captured.extend(records)

        store.upsert.side_effect = _capture
        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            return_value=[[0.1] * 1024, [0.2] * 1024],
        ):
            index_cards(store=store, vault_path=vault)

        kinds = {r.metadata.get("source_kind") for r in captured}
        assert "card_project" in kinds
        assert "card_company" in kinds
