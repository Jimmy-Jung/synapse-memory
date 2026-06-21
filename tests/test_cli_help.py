"""CLI help wording for provider-only compatibility flags.

저자: JunyoungJung
작성일: 2026-06-21
"""

from __future__ import annotations

import pytest

import synapse_memory.cli as cli


def _help_output(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exc:
        cli.main([*argv, "--help"])
    assert exc.value.code == 0
    return capsys.readouterr().out


def test_ask_help_describes_hybrid_as_provider_only_compatibility(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _help_output(["ask"], capsys)

    assert "provider 선별" in out
    assert "provider-only에서는 ranking 차이 없음" in out
    assert "BM25" not in out
    assert "RRF" not in out


def test_persona_recall_help_describes_hybrid_as_provider_only_compatibility(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _help_output(["persona", "what-did-i-think"], capsys)

    assert "provider-only에서는 ranking 차이 없음" in out
    assert "BM25" not in out
    assert "RRF" not in out
