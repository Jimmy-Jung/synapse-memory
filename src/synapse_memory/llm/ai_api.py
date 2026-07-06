"""Provider-agnostic AI API facade."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, TypeAlias, cast

from synapse_memory.llm import claude, codex
from synapse_memory.llm._runtime import (
    CompleteOptions,
    ConcreteProvider,
    ProviderEnvironment,
    ProviderModule,
    make_options,
    options_kwargs,
    with_env,
)
from synapse_memory.retrieval.provider import _provider

AIProvider: TypeAlias = Literal["auto", "claude", "codex"]
ConcreteAIProvider: TypeAlias = ConcreteProvider
AIProviderEnv: TypeAlias = ProviderEnvironment

AI_PROVIDER_ENV_VAR = "SYNAPSE_AI_PROVIDER"
DEFAULT_PROVIDER: ConcreteAIProvider = "codex"
DEFAULT_TIMEOUT_SEC = 120


class AIError(RuntimeError):
    """Provider-agnostic AI call failure."""


class AIUnavailableError(AIError):
    """Selected AI provider is unavailable."""


@dataclass(frozen=True)
class AIEnvironment:
    provider: ConcreteAIProvider
    provider_env: ProviderEnvironment

    @property
    def model(self) -> str:
        return self.provider_env.model

    @property
    def path(self) -> str | None:
        return self.provider_env.path

    @property
    def version(self) -> str | None:
        return self.provider_env.version

    @property
    def ready(self) -> bool:
        return self.provider_env.ready

    def reasons_unavailable(self) -> list[str]:
        return self.provider_env.reasons_unavailable()


PROVIDER_MODULES: dict[ConcreteAIProvider, ProviderModule] = {
    "claude": cast(ProviderModule, claude),
    "codex": cast(ProviderModule, codex),
}


def detect_ai_environment(
    provider: AIProvider | None = None,
    *,
    model: str | None = None,
) -> AIEnvironment:
    resolved = _resolve_provider(provider)
    module = PROVIDER_MODULES[resolved]
    return AIEnvironment(
        provider=resolved,
        provider_env=module.detect_environment(model or module.DEFAULT_MODEL),
    )


def _complete_text(prompt: str, kwargs: dict[str, Any]) -> str:
    module, options = _resolve_call(kwargs)
    try:
        return module.complete(prompt, **options_kwargs(options))
    except Exception as exc:
        _raise_provider_error(exc, module)


def _complete_structured(prompt: str, kwargs: dict[str, Any]) -> Any:
    module, options = _resolve_call(kwargs)
    try:
        return module.complete_structured(prompt, **options_kwargs(options))
    except Exception as exc:
        _raise_provider_error(exc, module)


AICall = Callable[[str, dict[str, Any]], Any]


def _make_ai_call(runner: AICall, *, name: str) -> Callable[..., Any]:
    def call(prompt: str, **kwargs: Any) -> Any:
        return runner(prompt, kwargs)

    call.__name__ = name
    return call


complete = cast(Callable[..., str], _make_ai_call(_complete_text, name="complete"))
complete_structured = _make_ai_call(
    _complete_structured,
    name="complete_structured",
)


def _resolve_call(kwargs: dict[str, Any]) -> tuple[ProviderModule, CompleteOptions]:
    provider = _pop_provider(kwargs)
    options = make_options(default_timeout=DEFAULT_TIMEOUT_SEC, kwargs=kwargs)
    resolved = _coerce_env(options.env, provider=provider, model=options.model)
    return PROVIDER_MODULES[resolved.provider], with_env(options, resolved.provider_env)


def _pop_provider(kwargs: dict[str, Any]) -> AIProvider | None:
    if "provider" not in kwargs:
        return None
    return cast(AIProvider | None, kwargs.pop("provider"))


def _coerce_env(
    env: AIEnvironment | AIProviderEnv | None,
    *,
    provider: AIProvider | None,
    model: str | None,
) -> AIEnvironment:
    if isinstance(env, AIEnvironment):
        return env
    if env is not None:
        env_provider = getattr(env, "provider", None)
        if env_provider in PROVIDER_MODULES:
            return AIEnvironment(
                provider=cast(ConcreteAIProvider, env_provider),
                provider_env=cast(ProviderEnvironment, env),
            )
    return detect_ai_environment(provider, model=model)


def _resolve_provider(provider: AIProvider | None) -> ConcreteAIProvider:
    requested = (
        provider or os.environ.get(AI_PROVIDER_ENV_VAR) or _provider() or "auto"
    ).lower()
    if requested == "auto":
        return _runtime_provider()
    if requested in {"claude", "codex"}:
        return cast(ConcreteAIProvider, requested)
    raise ValueError(f"unknown AI provider: {requested}")


def _runtime_provider() -> ConcreteAIProvider:
    if _is_codex_runtime():
        return "codex"
    if _is_claude_runtime():
        return "claude"
    return DEFAULT_PROVIDER


def _is_codex_runtime() -> bool:
    return any(
        os.environ.get(name)
        for name in (
            "CODEX_CI",
            "CODEX_THREAD_ID",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        )
    )


def _is_claude_runtime() -> bool:
    return any(
        os.environ.get(name)
        for name in (
            "CLAUDECODE",
            "CLAUDE_CODE",
            "CLAUDE_PROJECT_DIR",
        )
    )


def _raise_provider_error(exc: Exception, module: ProviderModule) -> NoReturn:
    if isinstance(exc, module.ProviderUnavailableError):
        raise AIUnavailableError(str(exc)) from exc
    if isinstance(exc, module.ProviderError):
        raise AIError(str(exc)) from exc
    raise exc
