"""provider별 GPT-5.6 작업 모델 해석 테스트.

Codex 작업은 Sol/Terra/Luna tier로, Claude 작업은 기존 모델로 해석되는지
검증한다. (Codex에 Claude 모델을 전달하던 회귀도 함께 방어.)

저자: JunyoungJung
작성일: 2026-07-07
"""
from __future__ import annotations

from synapse_memory.config import (
    ModelsConfig,
    ModelTasksConfig,
    ProviderModelOverrideConfig,
    ProviderModelOverridesConfig,
)


def test_provider_default_fills_none_task() -> None:
    m = ModelsConfig()
    assert m.model_for_task("codex", "ask") == "gpt-5.6-sol"
    assert m.model_for_task("claude", "ask") == "sonnet"


def test_explicit_task_and_override_still_win() -> None:
    m = ModelsConfig()
    assert m.model_for_task("codex", "classify") == "gpt-5.6-luna"
    assert m.model_for_task("claude", "classify") == "haiku"  # provider override
    assert m.model_for_task("claude", "resume") == "sonnet"  # None → claude default


def test_provider_task_override_wins_over_shared_task_default() -> None:
    """models.overrides.<provider>.<task>는 models.tasks.<task>보다 우선한다."""
    m = ModelsConfig(
        tasks=ModelTasksConfig(ask="shared-task-model"),
        overrides=ProviderModelOverridesConfig(
            codex=ProviderModelOverrideConfig(ask="codex-ask-override")
        ),
    )

    assert m.model_for_task("codex", "ask") == "codex-ask-override"
    assert m.model_for_task("claude", "ask") == "shared-task-model"


def test_codex_tasks_use_the_right_gpt_5_6_tier() -> None:
    m = ModelsConfig()

    assert m.model_for_task("codex", "relevance") == "gpt-5.6-luna"
    assert m.model_for_task("codex", "card_generate") == "gpt-5.6-terra"
    assert m.model_for_task("codex", "recall") == "gpt-5.6-terra"
    assert m.model_for_task("codex", "update_profile") == "gpt-5.6-terra"
    assert m.model_for_task("codex", "generate") == "gpt-5.6-terra"
    assert m.model_for_task("codex", "ask") == "gpt-5.6-sol"
    assert m.model_for_task("codex", "decide") == "gpt-5.6-sol"
    assert m.model_for_task("codex", "resume") == "gpt-5.6-sol"


def test_fallback_map_when_no_default_field() -> None:
    # config override 블록에 default 미지정이어도 안전망 폴백
    m = ModelsConfig(
        overrides=ProviderModelOverridesConfig(codex=ProviderModelOverrideConfig())
    )
    assert m.model_for_task("codex", "ask") == "gpt-5.6-terra"


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
    for name in (
        "CODEX_CI",
        "CODEX_THREAD_ID",
        "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        config_mod, "get_config", lambda: SynapseConfig(ai_provider="codex")
    )

    assert common._resolve_model(None, "ask") == "gpt-5.6-sol"

    # config=auto일 때만 runtime 감지 사용 → claude 모델
    monkeypatch.setattr(
        config_mod, "get_config", lambda: SynapseConfig(ai_provider="auto")
    )
    assert common._resolve_model(None, "ask") == "sonnet"
