"""대화형 endpoint(ask / me *) 의 _interactive_guard 동작 검증."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse_memory.cli import _interactive_guard


def test_env_var_skips_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNAPSE_FROM_AGENT=1 이면 (TTY 든 아니든) 경고/대기 모두 생략."""
    monkeypatch.setenv("SYNAPSE_FROM_AGENT", "1")
    monkeypatch.setattr("synapse_memory.cli._stdout_is_tty", lambda: True)
    with patch("synapse_memory.cli.time.sleep") as mock_sleep:
        _interactive_guard("ask", "ask")
    assert mock_sleep.call_count == 0


def test_pipe_stdout_skips_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdout 이 pipe(=자동화) 이면 경고/대기 생략."""
    monkeypatch.delenv("SYNAPSE_FROM_AGENT", raising=False)
    monkeypatch.setattr("synapse_memory.cli._stdout_is_tty", lambda: False)
    with patch("synapse_memory.cli.time.sleep") as mock_sleep:
        _interactive_guard("ask", "ask")
    assert mock_sleep.call_count == 0


def test_tty_human_triggers_warning_and_sleep(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """TTY + env 없음 = 사람의 직접 호출 → 경고 + 3초 대기."""
    monkeypatch.delenv("SYNAPSE_FROM_AGENT", raising=False)
    monkeypatch.setattr("synapse_memory.cli._stdout_is_tty", lambda: True)
    with patch("synapse_memory.cli.time.sleep") as mock_sleep:
        _interactive_guard("persona decide", "decide")
    captured = capsys.readouterr()
    assert "LLM 대화 컨텍스트" in captured.err
    assert "/synapse-decide" in captured.err
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(3)


def test_guard_message_includes_command_label(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """command 라벨이 경고 본문에 포함되어 어떤 endpoint 인지 명확하다."""
    monkeypatch.delenv("SYNAPSE_FROM_AGENT", raising=False)
    monkeypatch.setattr("synapse_memory.cli._stdout_is_tty", lambda: True)
    with patch("synapse_memory.cli.time.sleep"):
        _interactive_guard("persona draft-resume", "resume")
    captured = capsys.readouterr()
    assert "persona draft-resume" in captured.err
    assert "/synapse-resume" in captured.err
