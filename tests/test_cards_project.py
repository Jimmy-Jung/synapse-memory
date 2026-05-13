"""Project Card 모듈 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.cards.project import (
    DEFAULT_PROJECTS_SUBPATH,
    ProjectCard,
    ProjectMetric,
    ProjectSource,
    list_project_cards,
    load_project_card,
    parse_project_card,
    projects_dir,
    save_project_card,
    serialize_project_card,
    slugify,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """가짜 vault."""
    v = tmp_path / "vault"
    v.mkdir()
    return v


# ---------------------------------------------------------------------------
# 직렬화 round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_minimal_card(self) -> None:
        card = ProjectCard(
            project_id="dansim-ios",
            display_name="단심 (명상 앱)",
            body="## 문제\n간단",
        )
        text = serialize_project_card(card)
        parsed = parse_project_card(text)
        assert parsed.project_id == "dansim-ios"
        assert parsed.display_name == "단심 (명상 앱)"
        assert "간단" in parsed.body

    def test_full_card(self) -> None:
        card = ProjectCard(
            project_id="dansim-ios",
            display_name="단심",
            status="completed",
            role="iOS Lead",
            period_start="2023-09",
            period_end="2024-12",
            team_size=4,
            domains=["ios", "mobile"],
            stack=["Swift", "TCA"],
            keywords=["retention"],
            metrics=[
                ProjectMetric(name="D7 retention", before="18%", after="31%"),
                ProjectMetric(name="paid", value="2.1%"),
            ],
            links=["https://github.com/example/dansim"],
            sources=[
                ProjectSource(type="obsidian", path="10_Active/단심.md"),
            ],
            confidence=0.85,
            created="2026-05-10",
            last_reviewed="2026-05-10",
            body="## 문제\n복잡한 본문\n\n한국어 텍스트.",
        )
        text = serialize_project_card(card)
        parsed = parse_project_card(text)
        assert parsed.role == "iOS Lead"
        assert parsed.team_size == 4
        assert parsed.domains == ["ios", "mobile"]
        assert parsed.stack == ["Swift", "TCA"]
        assert len(parsed.metrics) == 2
        assert parsed.metrics[0].before == "18%"
        assert parsed.metrics[1].value == "2.1%"
        assert parsed.sources[0].type == "obsidian"
        assert parsed.confidence == 0.85
        assert "복잡한 본문" in parsed.body

    def test_korean_preserved(self) -> None:
        card = ProjectCard(
            project_id="korean-test",
            display_name="한글 프로젝트 — 명상앱",
            body="## 한국어 본문\n매우 긴 텍스트.",
        )
        text = serialize_project_card(card)
        # yaml에 한국어 그대로 저장 (escape 안 함)
        assert "한글 프로젝트" in text
        parsed = parse_project_card(text)
        assert parsed.display_name == "한글 프로젝트 — 명상앱"


# ---------------------------------------------------------------------------
# parsing 견고성
# ---------------------------------------------------------------------------


class TestParsing:
    def test_no_frontmatter_raises(self) -> None:
        with pytest.raises(ValueError, match="frontmatter"):
            parse_project_card("# 그냥 본문\n내용")

    def test_invalid_yaml_raises(self) -> None:
        bad = "---\n[invalid: yaml:: ::\n---\n본문"
        with pytest.raises(ValueError, match="yaml 파싱 실패"):
            parse_project_card(bad)

    def test_missing_required_raises(self) -> None:
        text = "---\nstatus: active\n---\n본문"
        with pytest.raises(ValueError, match="필수 필드 누락"):
            parse_project_card(text)

    def test_optional_fields_default(self) -> None:
        text = "---\nproject_id: test\ndisplay_name: Test\n---\n본문"
        card = parse_project_card(text)
        assert card.role is None
        assert card.domains == []
        assert card.metrics == []
        assert card.confidence == 1.0


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("단심 iOS", "단심-ios"),
            ("Hello World", "hello-world"),
            ("foo/bar baz", "foo-bar-baz"),
            ("  spaced  ", "spaced"),
            ("special!!!chars", "special-chars"),
            ("", "untitled"),
        ],
    )
    def test_examples(self, name: str, expected: str) -> None:
        assert slugify(name) == expected


# ---------------------------------------------------------------------------
# 디스크 I/O
# ---------------------------------------------------------------------------


class TestDiskIO:
    def test_save_and_load(self, vault: Path) -> None:
        card = ProjectCard(
            project_id="test-card",
            display_name="Test Card",
            role="Engineer",
            body="## 본문",
        )
        path = save_project_card(card, vault_path=vault)

        assert path.exists()
        assert path.relative_to(vault) == DEFAULT_PROJECTS_SUBPATH / "test-card.md"

        loaded = load_project_card("test-card", vault_path=vault)
        assert loaded.display_name == "Test Card"
        assert loaded.role == "Engineer"

    def test_load_missing_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_project_card("nonexistent", vault_path=vault)

    def test_overwrite_existing(self, vault: Path) -> None:
        card1 = ProjectCard(project_id="x", display_name="V1")
        save_project_card(card1, vault_path=vault)
        card2 = ProjectCard(project_id="x", display_name="V2")
        save_project_card(card2, vault_path=vault)

        loaded = load_project_card("x", vault_path=vault)
        assert loaded.display_name == "V2"

    def test_list_empty(self, vault: Path) -> None:
        assert list_project_cards(vault_path=vault) == []

    def test_list_sorted(self, vault: Path) -> None:
        for pid in ["zebra", "alpha", "delta"]:
            save_project_card(
                ProjectCard(project_id=pid, display_name=pid.title()),
                vault_path=vault,
            )
        cards = list_project_cards(vault_path=vault)
        assert [c.project_id for c in cards] == ["alpha", "delta", "zebra"]

    def test_list_skips_invalid_files(self, vault: Path) -> None:
        d = projects_dir(vault_path=vault)
        d.mkdir(parents=True)
        # 정상 1개
        save_project_card(
            ProjectCard(project_id="ok", display_name="OK"),
            vault_path=vault,
        )
        # 깨진 파일 — frontmatter 없음
        (d / "broken.md").write_text("그냥 텍스트", encoding="utf-8")

        cards = list_project_cards(vault_path=vault)
        assert len(cards) == 1
        assert cards[0].project_id == "ok"
