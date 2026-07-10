"""Provider-agnostic AI API facade tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse_memory.llm.ai_api import (
    AIEnvironment,
    AIError,
    detect_ai_environment,
    resolve_model_for_task,
)
from synapse_memory.llm.claude import ClaudeEnvironment, ClaudeError
from synapse_memory.llm.codex import CodexEnvironment


def test_auto_provider_uses_codex_runtime(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse_memory.config as config_module

    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "no_config.yaml")
    config_module.clear_cache()
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")

    with patch("synapse_memory.llm.ai_api.codex.detect_codex_environment") as detect:
        detect.return_value = CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.5")
        env = detect_ai_environment(model="gpt-5.5")

    assert env.provider == "codex"


def test_explicit_provider_uses_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_AI_PROVIDER", "claude")

    with patch("synapse_memory.llm.ai_api.claude.detect_claude_environment") as detect:
        detect.return_value = ClaudeEnvironment("/x/claude", "2.1", "sonnet")
        env = detect_ai_environment()

    assert env.provider == "claude"


def test_auto_provider_defaults_to_codex(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse_memory.config as config_module

    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.delenv("CODEX_CI", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "no_config.yaml")
    config_module.clear_cache()

    with patch("synapse_memory.llm.ai_api.codex.detect_codex_environment") as detect:
        detect.return_value = CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.5")
        env = detect_ai_environment()

    assert env.provider == "codex"


def test_configured_provider_overrides_runtime_detection(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse_memory.config as config_module

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("ai_provider: claude\n", encoding="utf-8")
    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", cfg_path)
    config_module.clear_cache()

    with patch("synapse_memory.llm.ai_api.claude.detect_claude_environment") as detect:
        detect.return_value = ClaudeEnvironment("/x/claude", "2.1", "sonnet")
        env = detect_ai_environment()

    assert env.provider == "claude"


def test_resolve_model_for_task_uses_effective_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import synapse_memory.config as config_module
    from synapse_memory.config import SynapseConfig

    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setattr(
        config_module, "get_config", lambda: SynapseConfig(ai_provider="codex")
    )

    assert resolve_model_for_task("ask") == "gpt-5.6-sol"
    assert resolve_model_for_task("relevance") == "gpt-5.6-luna"
    assert resolve_model_for_task("ask", provider="claude") == "sonnet"


def test_complete_dispatches_to_codex() -> None:
    from synapse_memory.llm import ai_api

    env = AIEnvironment(
        provider="codex",
        provider_env=CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.5"),
    )
    with patch("synapse_memory.llm.ai_api.codex.complete", return_value="ok") as complete:
        assert ai_api.complete("p", env=env) == "ok"

    complete.assert_called_once()


def test_complete_structured_keeps_model_override_with_injected_environment() -> None:
    """주입 환경은 provider 선택용이며 명시 model을 덮어쓰지 않는다."""
    from synapse_memory.llm import ai_api

    provider_env = CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.6-terra")
    env = AIEnvironment(provider="codex", provider_env=provider_env)
    with patch(
        "synapse_memory.llm.ai_api.codex.complete_structured",
        return_value={"related": []},
    ) as complete:
        assert (
            ai_api.complete_structured(
                "p",
                env=env,
                model="gpt-5.6-luna",
            )
            == {"related": []}
        )

    assert complete.call_args.kwargs["model"] == "gpt-5.6-luna"
    assert complete.call_args.kwargs["env"] is provider_env


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
