"""indexer.py 테스트 — embeddings/vector store 모두 mock.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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
from synapse_memory.feedback.events import append_feedback_event, build_feedback_event
from synapse_memory.rag.indexer import (
    PREFIX_COMPANY,
    PREFIX_PROJECT,
    VectorRecord,
    company_card_to_text,
    index_cards,
    project_card_to_text,
)
from synapse_memory.rag.vector_store import VectorStore
from synapse_memory.storage.l0 import L0_ENV_VAR


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

    def test_metadata_includes_feedback_score(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vault: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        save_project_card(
            ProjectCard(project_id="dansim-ios", display_name="단심"),
            vault_path=vault,
        )
        append_feedback_event(
            build_feedback_event(
                target_kind="card",
                target_ref="dansim-ios",
                action="reject",
                reason="관련 없음",
            )
        )
        store = self._fake_store()
        captured: list[VectorRecord] = []

        def _capture(records):
            captured.extend(records)

        store.upsert.side_effect = _capture
        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            return_value=[[0.1] * 1024],
        ):
            index_cards(store=store, vault_path=vault)

        assert captured[0].metadata["feedback_score"] == 0.85

    def test_include_raw_indexes_obsidian_and_redacted_claude(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vault: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        raw_note = vault / "10_Active" / "raw-note.md"
        raw_note.parent.mkdir(parents=True)
        raw_note.write_text("당근마켓 raw memo", encoding="utf-8")
        claude_log = tmp_path / "private" / "redacted" / "claude-code" / "session.jsonl"
        claude_log.parent.mkdir(parents=True)
        claude_log.write_text('{"text":"카카오뱅크 redacted memo"}', encoding="utf-8")

        store = self._fake_store()
        captured: list[VectorRecord] = []
        store.upsert.side_effect = lambda records: captured.extend(records)

        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            side_effect=lambda texts, **_kwargs: [[0.1] * 1024 for _ in texts],
        ):
            stats = index_cards(
                store=store,
                vault_path=vault,
                include_raw=True,
                bm25_path=tmp_path / "bm25.jsonl",
            )

        assert stats.raw_obsidian_chunks == 1
        assert stats.raw_claude_code_chunks == 1
        assert stats.bm25_documents == 2
        kinds = {record.metadata["source_kind"] for record in captured}
        assert "raw_obsidian" in kinds
        assert "raw_claude_code" in kinds

    def test_raw_chunk_ids_are_stable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vault: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        raw_note = vault / "10_Active" / "memo.md"
        raw_note.parent.mkdir(parents=True)
        raw_note.write_text("dansim-ios raw memo", encoding="utf-8")

        def run_once() -> list[str]:
            store = self._fake_store()
            captured: list[VectorRecord] = []
            store.upsert.side_effect = lambda records: captured.extend(records)
            with patch(
                "synapse_memory.rag.indexer.embed_texts",
                side_effect=lambda texts, **_kwargs: [[0.1] * 1024 for _ in texts],
            ):
                index_cards(
                    store=store,
                    vault_path=vault,
                    include_raw=True,
                    bm25_path=tmp_path / "bm25.jsonl",
                )
            return [record.id for record in captured if record.id.startswith("raw_")]

        assert run_once() == run_once()

    def test_include_raw_redacts_before_upsert(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vault: Path
    ) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))
        raw_note = vault / "10_Active" / "secret.md"
        raw_note.parent.mkdir(parents=True)
        raw_note.write_text("email user@example.com", encoding="utf-8")
        store = self._fake_store()
        captured: list[VectorRecord] = []
        store.upsert.side_effect = lambda records: captured.extend(records)

        with patch(
            "synapse_memory.rag.indexer.embed_texts",
            side_effect=lambda texts, **_kwargs: [[0.1] * 1024 for _ in texts],
        ), patch(
            "synapse_memory.rag.indexer.redact_full",
            side_effect=lambda text: SimpleNamespace(
                redacted=text.replace("user@example.com", "[EMAIL_1]")
            ),
        ):
            index_cards(
                store=store,
                vault_path=vault,
                include_raw=True,
                bm25_path=tmp_path / "bm25.jsonl",
            )

        raw_records = [record for record in captured if record.id.startswith("raw_")]
        assert raw_records
        assert "user@example.com" not in raw_records[0].document
        assert "[EMAIL_1]" in raw_records[0].document
