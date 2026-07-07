"""me endpoints — draft_resume 테스트 (020 provider-only).

벡터/임베딩 의존 제거. recipes pipeline 이 ``build_entity_index`` + ``select_related`` 로
Project entity 를 선별하므로, 실제 ProjectCard 를 vault 에 심고 ``select_related`` +
``ai_api_complete`` 만 monkeypatch 한다.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_memory.cards.company import (
    CompanyCard,
    JobPosition,
    save_company_card,
)
from synapse_memory.cards.project import ProjectCard, save_project_card
from synapse_memory.endpoints.persona import (
    DRAFTS_SUBPATH,
    ResumeDraft,
    _build_resume_prompt,
    _company_search_query,
    draft_resume,
)
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.recipes.pipeline import _CardMatch


def _ai_env() -> ClaudeEnvironment:
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


def _card_match(card_id: str, doc: str = "") -> _CardMatch:
    return _CardMatch(
        id=card_id,
        document=doc or f"# {card_id}",
        metadata={
            "source_kind": "card_project",
            "card_id": card_id,
            "display_name": card_id,
        },
    )


def _seed_project(vault: Path, project_id: str) -> None:
    save_project_card(
        ProjectCard(
            project_id=project_id,
            display_name=project_id,
            status="active",
            body=f"# {project_id} 본문",
        ),
        vault_path=vault,
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
            (_card_match("p1", "# P1\n내용"), 0.0),
            (_card_match("p2", "# P2\n내용"), 0.0),
        ]
        prompt = _build_resume_prompt(c, matched)
        assert "X" in prompt
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
        _seed_project(vault, "dansim")
        with patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=["dansim"],
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value=(
                "---\n"
                "title: 당근마켓 지원 이력서\n"
                "company_id: danggeun\n"
                "---\n\n# 한 줄 소개\niOS 개발자."
            ),
        ):
            result = draft_resume(
                "danggeun",
                vault_path=vault,
                ai_env=_ai_env(),
            )

        assert isinstance(result, ResumeDraft)
        assert result.company_id == "danggeun"
        assert result.company_name == "당근마켓"
        assert result.saved_path.exists()
        assert result.saved_path.parent.relative_to(vault) == DRAFTS_SUBPATH
        assert "당근마켓" in result.saved_path.name
        assert result.saved_path.suffix == ".md"
        assert "dansim" in result.project_card_ids

    def test_restricts_to_project_kind(self, vault: Path) -> None:
        self._setup_company(vault)
        _seed_project(vault, "x")
        from synapse_memory.recipes import pipeline as pipeline_mod

        with patch.object(
            pipeline_mod, "build_entity_index", wraps=pipeline_mod.build_entity_index
        ) as mock_build, patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=["x"],
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="---\ntitle: x\n---\n",
        ):
            draft_resume("danggeun", vault_path=vault, ai_env=_ai_env())
        # resume recipe rag_filter=card_project → kinds=("project",)
        assert mock_build.call_args.kwargs["kinds"] == ("project",)

    def test_missing_company_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            draft_resume("nonexistent", vault_path=vault, ai_env=_ai_env())

    def test_no_matches_raises(self, vault: Path) -> None:
        self._setup_company(vault)
        _seed_project(vault, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=[],
        ), pytest.raises(ValueError, match="Project entity"):
            draft_resume("danggeun", vault_path=vault, ai_env=_ai_env())

    def test_top_k_passed_to_select(self, vault: Path) -> None:
        self._setup_company(vault)
        _seed_project(vault, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=["x"],
        ) as mock_select, patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="---\ntitle: x\n---\n",
        ):
            draft_resume(
                "danggeun",
                top_k_projects=10,
                vault_path=vault,
                ai_env=_ai_env(),
            )
        assert mock_select.call_args.kwargs["max_pages"] == 10

    def test_filename_includes_company_and_yearmonth(self, vault: Path) -> None:
        self._setup_company(vault)
        _seed_project(vault, "x")
        with patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=["x"],
        ), patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value="---\ntitle: x\n---\n",
        ):
            result = draft_resume("danggeun", vault_path=vault, ai_env=_ai_env())
        assert re.match(
            r"Resume - 당근마켓 \(\d{4}-\d{2}\)\.md", result.saved_path.name
        )
