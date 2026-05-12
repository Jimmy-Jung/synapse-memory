"""T017 — Recipe generator end-to-end RED test (US1: weekly_report).

Covers spec User Story 1 + SC-002 (builtin recipes produce non-empty markdown
and save to declared paths in fixture vault).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from synapse_memory.recipes import generate

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "recipes_vault"
_BUILTIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "synapse_memory"
    / "recipes"
    / "builtin"
)


class _StoreStub:
    """Mimics ``store.query(...) -> list[(VectorRecord, distance)]``."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def query(self, *_args: Any, **_kwargs: Any) -> list[tuple[Any, float]]:
        out: list[tuple[Any, float]] = []
        for i, meta in enumerate(self._records):
            rec = mock.Mock()
            rec.metadata = meta
            rec.document = meta.get("document", "")
            rec.id = meta.get("card_id", f"rec-{i}")
            out.append((rec, 0.10 + 0.01 * i))
        return out


@pytest.fixture
def fixture_vault(tmp_path: Path) -> Path:
    """Copy the fixture vault tree to ``tmp_path`` so tests can mutate it."""
    dst = tmp_path / "vault"
    shutil.copytree(_FIXTURE_ROOT, dst)
    return dst


def test_weekly_report_end_to_end(fixture_vault: Path) -> None:
    """US1 — fixture vault + builtin weekly_report → markdown saved + last_answer."""
    captured: dict[str, str] = {}

    def fake_complete(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["prompt"] = prompt
        captured["system"] = system or ""
        return (
            "---\n"
            "title: 주간 보고 2026-W19\n"
            "period: 2026-W19\n"
            "generated: 2026-05-12\n"
            "based_on:\n"
            "  - card_project:prj-2026-w19-alpha\n"
            "  - card_project:prj-2026-w19-beta\n"
            "---\n\n"
            "## 이번 주 한 일\n"
            "- Synapse Memory v0.5 alpha 진행 [prj-2026-w19-alpha]\n"
            "- Recipe spec kit lockdown [prj-2026-w19-beta]\n"
            "## 핵심 의사결정\n- ...\n"
            "## 다음 주 계획\n- ...\n"
        )

    store = _StoreStub([
        {
            "card_id": "prj-2026-w19-alpha",
            "display_name": "Synapse Memory v0.5 alpha",
            "source_kind": "card_project",
            "document": "이번 주의 핵심 작업: recipe framework 설계.",
        },
        {
            "card_id": "prj-2026-w19-beta",
            "display_name": "Recipe spec kit lockdown",
            "source_kind": "card_project",
            "document": "clarify Q1-Q5 lock + plan/research 작성.",
        },
    ])

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        side_effect=fake_complete,
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "fake_last_response.json",
    ):
        result = generate(
            "weekly_report",
            inputs={"period": "2026-W19"},
            vault_path=fixture_vault,
            store=store,
            builtin_dir=_BUILTIN_DIR,
        )

    # 결과 markdown
    assert "이번 주 한 일" in result.answer_markdown
    assert "prj-2026-w19-alpha" in result.answer_markdown
    assert result.profile_used is True

    # 저장 경로 (R-5 filename rule + save_subpath=30_Creative/Reports)
    assert result.saved_path is not None
    assert result.saved_path.is_file()
    assert "30_Creative/Reports" in str(result.saved_path)
    assert "weekly_report - 2026-W19" in result.saved_path.name

    # AI prompt 에 Profile 본문 + ProjectCard citations 가 모두 포함
    assert "명료한 글쓰기" in captured["prompt"]
    assert "prj-2026-w19-alpha" in captured["prompt"]

    # System prompt 의 placeholder 가 렌더됨
    assert "2026-W19" in captured["system"]
    assert "한국어" in captured["system"]

    # last_answer ref
    assert result.last_answer_ref is not None
    assert result.last_answer_ref.command == "me.generate.weekly_report"
    assert "2026-W19" in result.last_answer_ref.query
    assert len(result.last_answer_ref.citations) >= 1


# ----- US2: Resume voice·locale·domain (T025-T028) -----------------------------


def _swap_profile(vault: Path, variant: str) -> None:
    """fixture vault 의 90_System/AI/Profile.md 를 variant 디렉터리 내용으로 교체."""
    src = vault / variant / "90_System" / "AI" / "Profile.md"
    dst = vault / "90_System" / "AI" / "Profile.md"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _set_company_resume_language(vault: Path, lang: str) -> None:
    """fixture acme_co.md 의 frontmatter 에 resume_language 를 삽입."""
    p = vault / "20_Reference" / "Companies" / "acme_co.md"
    text = p.read_text(encoding="utf-8")
    # frontmatter 끝(--- 단독 줄) 직전에 한 줄 추가
    lines = text.split("\n")
    # frontmatter 의 두 번째 --- 위치
    closing = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = i
            break
    assert closing > 0, "fixture frontmatter missing closing ---"
    lines.insert(closing, f"resume_language: {lang}")
    p.write_text("\n".join(lines), encoding="utf-8")


def _resume_store() -> _StoreStub:
    return _StoreStub([
        {
            "card_id": "prj-2026-w19-alpha",
            "display_name": "Synapse Memory v0.5 alpha",
            "source_kind": "card_project",
            "document": "Backend + LLM 통합 경험. recipe framework 설계.",
        },
    ])


def test_resume_locale_english_from_profile(fixture_vault: Path) -> None:
    """T025 — Profile.preferred_lang=en → locale_source=profile, locale=English."""
    _swap_profile(fixture_vault, "profile_en_design")

    captured: dict[str, str] = {}

    def fake_complete(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["prompt"] = prompt
        captured["system"] = system or ""
        return "# Resume body (mock)"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake_complete
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "ignored.json",
    ):
        result = generate(
            "resume",
            inputs={"company_id": "acme_co"},
            vault_path=fixture_vault,
            store=_resume_store(),
            builtin_dir=_BUILTIN_DIR,
        )

    assert result.locale == "English"
    assert result.locale_source == "profile"
    # Profile body 가 user prompt 에 첨부됨
    assert "Designer Test User" in captured["prompt"]


def test_resume_company_card_locale_wins_over_profile(fixture_vault: Path) -> None:
    """T026 — CompanyCard.resume_language=en + Profile.preferred_lang=한국어 → locale_source=company_card."""
    # base Profile.md 는 preferred_lang=한국어 (fixture default)
    _set_company_resume_language(fixture_vault, "en")

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        return_value="# Resume (mock)",
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "ignored.json",
    ):
        result = generate(
            "resume",
            inputs={"company_id": "acme_co"},
            vault_path=fixture_vault,
            store=_resume_store(),
            builtin_dir=_BUILTIN_DIR,
        )

    assert result.locale == "English"
    assert result.locale_source == "company_card"


def test_resume_domain_research_sections(fixture_vault: Path) -> None:
    """T027 — Profile.domain=research → domain="research" + system_prompt 에 Publications/Methodology 가이드 존재."""
    _swap_profile(fixture_vault, "profile_en_research")

    captured: dict[str, str] = {}

    def fake_complete(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["system"] = system or ""
        return "# mock research resume"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake_complete
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "ignored.json",
    ):
        result = generate(
            "resume",
            inputs={"company_id": "acme_co"},
            vault_path=fixture_vault,
            store=_resume_store(),
            builtin_dir=_BUILTIN_DIR,
        )

    assert result.domain == "research"
    assert result.domain_source == "profile"
    # rendered system_prompt 에 research 도메인 가이드가 모두 포함됨
    assert "Publications" in captured["system"]
    assert "Grants" in captured["system"]
    assert "Methodology" in captured["system"]


def test_resume_domain_design_sections(fixture_vault: Path) -> None:
    """T028 — Profile.domain=design → domain="design" + system_prompt 에 Case Studies/Tools 가이드."""
    _swap_profile(fixture_vault, "profile_en_design")

    captured: dict[str, str] = {}

    def fake_complete(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["system"] = system or ""
        return "# mock design resume"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake_complete
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "ignored.json",
    ):
        result = generate(
            "resume",
            inputs={"company_id": "acme_co"},
            vault_path=fixture_vault,
            store=_resume_store(),
            builtin_dir=_BUILTIN_DIR,
        )

    assert result.domain == "design"
    assert result.domain_source == "profile"
    assert "Case Studies" in captured["system"]
    assert "Tools" in captured["system"]


def test_resume_default_korean_when_profile_has_no_frontmatter(
    fixture_vault: Path,
) -> None:
    """spec User Story 2 AC#3 — Profile frontmatter 없고 CompanyCard 도 resume_language 없으면 한국어/generic fallback."""
    _swap_profile(fixture_vault, "profile_default")

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", return_value="ok"
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "ignored.json",
    ):
        result = generate(
            "resume",
            inputs={"company_id": "acme_co"},
            vault_path=fixture_vault,
            store=_resume_store(),
            builtin_dir=_BUILTIN_DIR,
        )

    assert result.locale == "한국어"
    assert result.locale_source == "default"
    assert result.domain == "generic"
    assert result.domain_source == "default"
