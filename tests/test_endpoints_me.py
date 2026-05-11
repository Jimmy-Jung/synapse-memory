"""me endpoints — draft_resume 테스트.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import synapse_memory.endpoints.me as me_mod
from synapse_memory.cards.company import (
    CompanyCard,
    JobPosition,
    save_company_card,
)
from synapse_memory.endpoints.me import (
    DRAFTS_SUBPATH,
    ResumeDraft,
    _build_resume_prompt,
    _company_search_query,
    draft_resume,
)
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.rag.vector_store import VectorRecord


def _claude_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.x",
        model="sonnet",
    )


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


def _mock_record(card_id: str, doc: str = "") -> VectorRecord:
    return VectorRecord(
        id=f"card_project:{card_id}",
        document=doc or f"# {card_id}",
        embedding=[0.0],
        metadata={
            "source_kind": "card_project",
            "card_id": card_id,
            "display_name": card_id,
        },
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class TestCompanySearchQuery:
    def test_minimal(self) -> None:
        c = CompanyCard(company_id="x", display_name="X Corp")
        q = _company_search_query(c)
        assert "X Corp" in q

    def test_includes_positions_and_keywords(self) -> None:
        c = CompanyCard(
            company_id="x",
            display_name="X",
            positions=[
                JobPosition(
                    title="Senior iOS",
                    seniority="senior",
                    keywords=["Swift", "TCA"],
                )
            ],
            body="우리는 iOS 앱을 만드는 회사",
        )
        q = _company_search_query(c)
        assert "Senior iOS" in q
        assert "Swift" in q
        assert "TCA" in q
        assert "senior" in q


class TestBuildPrompt:
    def test_includes_all_cards(self) -> None:
        c = CompanyCard(company_id="x", display_name="X")
        matched = [
            (_mock_record("p1", "# P1\n내용"), 0.4),
            (_mock_record("p2", "# P2\n내용"), 0.5),
        ]
        prompt = _build_resume_prompt(c, matched)
        assert "# X" in prompt or "X" in prompt
        assert "[p1]" in prompt
        assert "[p2]" in prompt
        assert "P1" in prompt and "P2" in prompt


# ---------------------------------------------------------------------------
# draft_resume
# ---------------------------------------------------------------------------


class TestDraftResume:
    def _setup_company(self, vault: Path) -> None:
        save_company_card(
            CompanyCard(
                company_id="danggeun",
                display_name="당근마켓",
                country="KR",
                positions=[
                    JobPosition(
                        title="Senior iOS",
                        keywords=["Swift", "mobile"],
                    )
                ],
                body="중고거래 플랫폼",
            ),
            vault_path=vault,
        )

    def test_creates_markdown_in_drafts(self, vault: Path) -> None:
        self._setup_company(vault)
        store = MagicMock()
        store.query.return_value = [
            (_mock_record("dansim", "# 단심\n## 영향\nretention 18%→31%"), 0.4),
            (_mock_record("이력서-2026", "# iOS 클린 아키텍처"), 0.45),
        ]

        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch.object(
            me_mod.claude_api,
            "complete",
            return_value=(
                "---\n"
                "title: 당근마켓 지원 이력서\n"
                "company_id: danggeun\n"
                "generated: 2026-05-10\n"
                "based_on:\n"
                "  - card_project:dansim\n"
                "---\n\n"
                "# 한 줄 소개\n"
                "iOS 개발자."
            ),
        ):
            result = draft_resume(
                "danggeun",
                vault_path=vault,
                store=store,
                claude_env=_claude_env(),
            )

        assert isinstance(result, ResumeDraft)
        assert result.company_id == "danggeun"
        assert result.company_name == "당근마켓"
        assert result.saved_path.exists()
        # 저장 위치: <vault>/30_Creative/Drafts/Resume - 당근마켓 (YYYY-MM).md
        assert result.saved_path.parent.relative_to(vault) == DRAFTS_SUBPATH
        assert "당근마켓" in result.saved_path.name
        assert result.saved_path.suffix == ".md"
        assert "dansim" in result.project_card_ids

    def test_passes_project_filter(self, vault: Path) -> None:
        self._setup_company(vault)
        store = MagicMock()
        store.query.return_value = [(_mock_record("x"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch.object(
            me_mod.claude_api, "complete", return_value="---\ntitle: x\n---\n"
        ):
            draft_resume("danggeun", vault_path=vault, store=store, claude_env=_claude_env())
        kw = store.query.call_args.kwargs
        assert kw["where"] == {"source_kind": "card_project"}

    def test_missing_company_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            draft_resume(
                "nonexistent",
                vault_path=vault,
                store=MagicMock(),
                claude_env=_claude_env(),
            )

    def test_no_matches_raises(self, vault: Path) -> None:
        self._setup_company(vault)
        store = MagicMock()
        store.query.return_value = []
        with patch.object(me_mod, "embed_query", return_value=[0.0]):
            with pytest.raises(ValueError, match="ProjectCard"):
                draft_resume(
                    "danggeun",
                    vault_path=vault,
                    store=store,
                    claude_env=_claude_env(),
                )

    def test_top_k_passed(self, vault: Path) -> None:
        self._setup_company(vault)
        store = MagicMock()
        store.query.return_value = [(_mock_record("x"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch.object(
            me_mod.claude_api, "complete", return_value="---\ntitle: x\n---\n"
        ):
            draft_resume(
                "danggeun",
                top_k_projects=10,
                vault_path=vault,
                store=store,
                claude_env=_claude_env(),
            )
        assert store.query.call_args.kwargs["top_k"] == 10

    def test_filename_includes_company_and_yearmonth(self, vault: Path) -> None:
        self._setup_company(vault)
        store = MagicMock()
        store.query.return_value = [(_mock_record("x"), 0.4)]
        with patch.object(me_mod, "embed_query", return_value=[0.0]), patch.object(
            me_mod.claude_api, "complete", return_value="---\ntitle: x\n---\n"
        ):
            result = draft_resume(
                "danggeun", vault_path=vault, store=store, claude_env=_claude_env()
            )
        # 형식: Resume - 당근마켓 (YYYY-MM).md
        import re
        assert re.match(
            r"Resume - 당근마켓 \(\d{4}-\d{2}\)\.md", result.saved_path.name
        )
