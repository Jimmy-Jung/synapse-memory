"""Step 5 llm facade shape tests.

저자: JunyoungJung
작성일: 2026-07-06
"""

from __future__ import annotations

from synapse_memory.llm import ai_api
from synapse_memory.llm.codex import CodexEnvironment


def test_provider_registry_is_module_based() -> None:
    assert "AIProviderAdapter" not in ai_api.__dict__
    assert ai_api.PROVIDER_MODULES["codex"] is ai_api.codex


def test_complete_accepts_provider_environment_protocol(monkeypatch) -> None:
    env = CodexEnvironment("/x/codex", "codex 1.0", "gpt-5.5")
    seen: dict[str, object] = {}

    def fake_complete(prompt: str, **kwargs: object) -> str:
        seen["prompt"] = prompt
        seen["env"] = kwargs["env"]
        return "ok"

    monkeypatch.setattr(ai_api.codex, "complete", fake_complete)

    assert ai_api.complete("p", env=env) == "ok"
    assert seen == {"prompt": "p", "env": env}
