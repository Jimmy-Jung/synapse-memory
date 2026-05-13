"""Card 자동 생성 테스트.

AI provider API는 mock — yaml 파싱 + 저장 흐름 검증.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_memory.cards.auto_generate import (
    _gather_redacted_text,
    _strip_outer_fence,
    generate_company_card,
    generate_project_card,
)
from synapse_memory.clusters.identify import ProjectCluster
from synapse_memory.llm.ai_api import AIError
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.llm.claude import ClaudeEnvironment


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.x",
        model="sonnet",
    )


def _apfel_disabled() -> ApfelEnvironment:
    return ApfelEnvironment(None, None, "0", False)


@pytest.fixture
def obs_root(tmp_path: Path) -> Path:
    root = tmp_path / "obs"
    root.mkdir()
    return root


def _make_cluster(cid: str, files: list[str], folder: str | None = None) -> ProjectCluster:
    return ProjectCluster(
        cluster_id=cid,
        candidate_name=cid,
        obsidian_files=list(files),
        vault_folders={folder} if folder else set(),
        seed_kind="vault" if folder else "claude_code",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestGatherRedacted:
    def test_collects_files(self, obs_root: Path) -> None:
        for i in range(3):
            (obs_root / f"n{i}.md").write_text(f"내용 {i}", encoding="utf-8")
        cluster = _make_cluster("x", [f"n{i}.md" for i in range(3)])
        text = _gather_redacted_text(
            cluster, obs_root, apfel_env=_apfel_disabled()
        )
        for i in range(3):
            assert f"내용 {i}" in text

    def test_empty_when_no_files(self, obs_root: Path) -> None:
        cluster = _make_cluster("x", [])
        text = _gather_redacted_text(cluster, obs_root, apfel_env=_apfel_disabled())
        assert text == ""


class TestStripFence:
    def test_yaml_fence(self) -> None:
        s = "```yaml\n---\nproject_id: x\n---\n# Body\n```"
        assert "yaml" not in _strip_outer_fence(s)
        assert "project_id: x" in _strip_outer_fence(s)

    def test_no_fence(self) -> None:
        s = "---\nx: 1\n---\n# Body"
        cleaned = _strip_outer_fence(s)
        assert cleaned.startswith("---")

    def test_prose_prefix_stripped(self) -> None:
        """Claude가 yaml 앞에 prose 추가한 경우 → frontmatter 위치 찾기."""
        s = (
            "★ Insight: 이 cluster는 흥미롭습니다.\n"
            "분석 결과:\n"
            "\n"
            "---\n"
            "project_id: foo\n"
            "display_name: Foo\n"
            "---\n"
            "# Foo\n"
            "본문"
        )
        cleaned = _strip_outer_fence(s)
        assert cleaned.startswith("---")
        assert "project_id: foo" in cleaned
        assert "★ Insight" not in cleaned

    def test_already_clean(self) -> None:
        s = "---\nproject_id: x\ndisplay_name: X\n---\n본문"
        assert _strip_outer_fence(s) == s


# ---------------------------------------------------------------------------
# generate_project_card
# ---------------------------------------------------------------------------


_GOOD_PROJECT_RESPONSE = """---
project_id: dansim
display_name: 단심 (명상 앱)
status: draft
role: iOS Lead
period_start: 2023-09
period_end: 2024-12
domains: [ios, mobile]
stack: [Swift, TCA]
keywords: [retention, gamification]
metrics:
  - { name: D7 retention, before: "18%", after: "31%" }
confidence: 0.7
---

# 단심 (명상 앱)

## 문제
사용자가 명상을 3일 만에 그만두는 retention 문제.

## 접근
Streak gamification + 적응형 알림.

## 영향
D7 retention 18% → 31%.

## 회고
TCA 도입은 잘했음.
"""


class TestGenerateProjectCard:
    def test_parses_response(self, obs_root: Path) -> None:
        (obs_root / "dansim.md").write_text("프로젝트 단심", encoding="utf-8")
        cluster = _make_cluster("dansim", ["dansim.md"])

        with patch(
            "synapse_memory.cards.auto_generate.ai_api.complete"
        ) as mock_complete:
            mock_complete.return_value = _GOOD_PROJECT_RESPONSE
            card = generate_project_card(
                cluster,
                candidate_name="단심",
                obs_root=obs_root,
                ai_env=_ai_env(),
                apfel_env=_apfel_disabled(),
            )

        assert card.project_id == "dansim"
        assert card.display_name == "단심 (명상 앱)"
        assert card.status == "draft"
        assert card.role == "iOS Lead"
        assert card.confidence == 0.7
        assert "Swift" in card.stack
        assert any(m.name == "D7 retention" for m in card.metrics)
        assert "단심" in card.body

    def test_fence_wrapped_response(self, obs_root: Path) -> None:
        (obs_root / "x.md").write_text("x", encoding="utf-8")
        cluster = _make_cluster("dansim", ["x.md"])

        wrapped = "```yaml\n" + _GOOD_PROJECT_RESPONSE + "```"
        with patch(
            "synapse_memory.cards.auto_generate.ai_api.complete"
        ) as mock_complete:
            mock_complete.return_value = wrapped
            card = generate_project_card(
                cluster,
                candidate_name="단심",
                obs_root=obs_root,
                ai_env=_ai_env(),
                apfel_env=_apfel_disabled(),
            )
        assert card.project_id == "dansim"

    def test_invalid_yaml_raises(self, obs_root: Path) -> None:
        (obs_root / "x.md").write_text("x", encoding="utf-8")
        cluster = _make_cluster("dansim", ["x.md"])

        with patch(
            "synapse_memory.cards.auto_generate.ai_api.complete"
        ) as mock_complete:
            mock_complete.return_value = "그냥 텍스트, frontmatter 없음"
            with pytest.raises(ValueError, match="frontmatter"):
                generate_project_card(
                    cluster,
                    candidate_name="x",
                    obs_root=obs_root,
                    ai_env=_ai_env(),
                    apfel_env=_apfel_disabled(),
                )

    def test_claude_error_propagates(self, obs_root: Path) -> None:
        (obs_root / "x.md").write_text("x", encoding="utf-8")
        cluster = _make_cluster("x", ["x.md"])

        with patch(
            "synapse_memory.cards.auto_generate.ai_api.complete"
        ) as mock_complete:
            mock_complete.side_effect = AIError("API 오류")
            with pytest.raises(AIError):
                generate_project_card(
                    cluster,
                    candidate_name="x",
                    obs_root=obs_root,
                    ai_env=_ai_env(),
                    apfel_env=_apfel_disabled(),
                )


# ---------------------------------------------------------------------------
# generate_company_card
# ---------------------------------------------------------------------------


_GOOD_COMPANY_RESPONSE = """---
company_id: danggeun
display_name: 당근마켓
status: target
country: KR
size: medium
website: https://www.daangn.com
positions:
  - { title: Senior iOS Engineer, seniority: senior, keywords: [Swift, mobile] }
confidence: 0.7
---

# 당근마켓

## 회사 개요
중고 거래 플랫폼.

## 기술 스택
iOS Swift, Android Kotlin.
"""


class TestGenerateCompanyCard:
    def test_parses_response(self, obs_root: Path) -> None:
        (obs_root / "danggeun.md").write_text("당근 정보", encoding="utf-8")
        cluster = _make_cluster("danggeun", ["danggeun.md"])

        with patch(
            "synapse_memory.cards.auto_generate.ai_api.complete"
        ) as mock_complete:
            mock_complete.return_value = _GOOD_COMPANY_RESPONSE
            card = generate_company_card(
                cluster,
                candidate_name="당근마켓",
                obs_root=obs_root,
                ai_env=_ai_env(),
                apfel_env=_apfel_disabled(),
            )

        assert card.company_id == "danggeun"
        assert card.display_name == "당근마켓"
        assert card.country == "KR"
        assert card.size == "medium"
        assert len(card.positions) == 1
        assert card.positions[0].title == "Senior iOS Engineer"
