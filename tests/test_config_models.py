"""provider별 기본 모델 해석 테스트.

task 기본값이 None일 때 provider 기본 모델(codex=gpt-5.5, claude=sonnet)로
폴백하는지 검증한다. (codex인데 sonnet으로 떨어지던 버그 회귀 방지.)

저자: JunyoungJung
작성일: 2026-07-07
"""
from __future__ import annotations

from synapse_memory.config import (
    ModelsConfig,
    ProviderModelOverrideConfig,
    ProviderModelOverridesConfig,
)


def test_provider_default_fills_none_task() -> None:
    m = ModelsConfig()
    # ask task 기본값 None → provider 기본 모델
    assert m.model_for_task("codex", "ask") == "gpt-5.5"
    assert m.model_for_task("claude", "ask") == "sonnet"


def test_explicit_task_and_override_still_win() -> None:
    m = ModelsConfig()
    assert m.model_for_task("codex", "classify") == "gpt-5.5"  # task base
    assert m.model_for_task("claude", "classify") == "haiku"  # provider override
    assert m.model_for_task("claude", "resume") == "sonnet"  # None → claude default


def test_fallback_map_when_no_default_field() -> None:
    # config override 블록에 default 미지정이어도 안전망 폴백
    m = ModelsConfig(
        overrides=ProviderModelOverridesConfig(codex=ProviderModelOverrideConfig())
    )
    assert m.model_for_task("codex", "ask") == "gpt-5.5"


def test_resolve_model_prefers_config_provider_over_runtime(monkeypatch) -> None:
    """Claude Code 세션 안에서 codex를 스폰해도 codex용 모델로 해석해야 한다.

    회귀: runtime 감지(claude)가 config(codex)를 이기면 codex CLI에 sonnet이
    전달되어 400이 난다. runtime은 config가 auto일 때만 참고.
    """
    import synapse_memory.cli.common as common
    import synapse_memory.config as config_mod
    from synapse_memory.config import SynapseConfig

    monkeypatch.setenv("CLAUDECODE", "1")  # Claude Code 세션 시뮬레이션
    monkeypatch.delenv("SYNAPSE_AI_PROVIDER", raising=False)
    monkeypatch.setattr(
        config_mod, "get_config", lambda: SynapseConfig(ai_provider="codex")
    )

    assert common._resolve_model(None, "ask") == "gpt-5.5"

    # config=auto일 때만 runtime 감지 사용 → claude 모델
    monkeypatch.setattr(
        config_mod, "get_config", lambda: SynapseConfig(ai_provider="auto")
    )
    assert common._resolve_model(None, "ask") == "sonnet"
