"""Provider-agnostic AI API facade tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse_memory.llm.ai_api import (
    AIEnvironment,
    AIError,
    detect_ai_environment,
)
from synapse_memory.llm.claude import ClaudeEnvironment, ClaudeError
from synapse_memory.llm.codex import CodexEnvironment


def test_auto_provider_uses_codex_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")

    with patch("synapse_memory.llm.ai_api.codex.detect_codex_environment") as detect:
        detect.return_value = CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.4")
        env = detect_ai_environment(model="gpt-5.4")

    assert env.provider == "codex"


def test_explicit_provider_uses_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_AI_PROVIDER", "claude")

    with patch("synapse_memory.llm.ai_api.claude.detect_claude_environment") as detect:
        detect.return_value = ClaudeEnvironment("/x/claude", "2.1", "sonnet")
        env = detect_ai_environment()

    assert env.provider == "claude"


def test_complete_dispatches_to_codex() -> None:
    from synapse_memory.llm import ai_api

    env = AIEnvironment(
        provider="codex",
        provider_env=CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.4"),
    )
    with patch("synapse_memory.llm.ai_api.codex.complete", return_value="ok") as complete:
        assert ai_api.complete("p", env=env) == "ok"

    complete.assert_called_once()


def test_complete_wraps_provider_errors() -> None:
    from synapse_memory.llm import ai_api

    env = AIEnvironment(
        provider="claude",
        provider_env=ClaudeEnvironment("/x/claude", "2.1", "sonnet"),
    )
    with patch(
        "synapse_memory.llm.ai_api.claude.complete",
        side_effect=ClaudeError("boom"),
    ), pytest.raises(AIError, match="boom"):
        ai_api.complete("p", env=env)

