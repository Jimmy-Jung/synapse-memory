"""T018 — `synapse-memory me generate` CLI RED test.

Covers spec User Story 1 (CLI 진입점) + Principle V (observability log line).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import synapse_memory.cli as cli_mod

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "recipes_vault"
_BUILTIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "synapse_memory"
    / "recipes"
    / "builtin"
)


@pytest.fixture
def fixture_vault(tmp_path: Path) -> Path:
    dst = tmp_path / "vault"
    shutil.copytree(_FIXTURE_ROOT, dst)
    return dst


def test_parser_registers_me_generate_subcommand() -> None:
    parser = cli_mod.build_parser()
    args = parser.parse_args(
        ["me", "generate", "weekly_report", "--input", "period=2026-W19"]
    )
    assert args.action == "generate"
    assert args.recipe == "weekly_report"
    assert "period=2026-W19" in args.input


def test_me_generate_weekly_report_invocation(
    fixture_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI 진입점 호출 → stdout markdown + stderr observability line + exit 0."""

    monkeypatch.setenv("SYNAPSE_FROM_AGENT", "1")

    class _StoreStub:
        def query(self, *_args: Any, **_kwargs: Any) -> list[tuple[Any, float]]:
            rec = mock.Mock()
            rec.metadata = {
                "card_id": "prj-2026-w19-alpha",
                "display_name": "Synapse Memory v0.5 alpha",
                "source_kind": "card_project",
            }
            rec.document = "이번 주의 핵심 작업"
            rec.id = "prj-2026-w19-alpha"
            return [(rec, 0.1)]

    def fake_complete(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        return "## 이번 주 한 일\n- [prj-2026-w19-alpha] 진행"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        side_effect=fake_complete,
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=fixture_vault / "fake_last_response.json",
    ), mock.patch(
        "synapse_memory.recipes.pipeline._BUILTIN_DIR_DEFAULT",
        _BUILTIN_DIR,
    ), mock.patch(
        "synapse_memory.cli.open_vector_store",
        return_value=_StoreStub(),
    ):
        rc = cli_mod.main(
            [
                "me",
                "generate",
                "weekly_report",
                "--input",
                "period=2026-W19",
                "--vault",
                str(fixture_vault),
            ]
        )

    captured = capsys.readouterr()
    assert rc == 0
    assert "이번 주 한 일" in captured.out
    assert "[me.generate.weekly_report]" in captured.err
    assert "profile_used=" in captured.err
    assert "matched=" in captured.err
    assert "[saved]" in captured.out
    assert "30_Creative/Reports" in captured.out


def test_me_generate_missing_required_input_exits_with_code(
    fixture_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """FR-014 — required input 누락 → non-zero exit code + stderr 메시지."""
    monkeypatch.setenv("SYNAPSE_FROM_AGENT", "1")

    class _EmptyStore:
        def query(self, *_args: Any, **_kwargs: Any) -> list[tuple[Any, float]]:
            return []

    with mock.patch(
        "synapse_memory.recipes.pipeline._BUILTIN_DIR_DEFAULT", _BUILTIN_DIR
    ), mock.patch(
        "synapse_memory.cli.open_vector_store", return_value=_EmptyStore()
    ):
        rc = cli_mod.main(
            [
                "me",
                "generate",
                "weekly_report",
                "--vault",
                str(fixture_vault),
            ]
        )

    err = capsys.readouterr().err
    assert rc != 0
    assert "period" in err
