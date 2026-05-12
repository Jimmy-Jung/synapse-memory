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
