"""Provider-agnostic AI API facade.

High-level endpoints depend on this module, not on a concrete Claude/Codex
runtime. New providers should add an adapter module and one registry entry here.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, Protocol, TypeAlias, cast

from synapse_memory.llm import claude, codex
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.llm.codex import CodexEnvironment
from synapse_memory.retrieval.provider import _provider

AIProvider: TypeAlias = Literal["auto", "claude", "codex"]
ConcreteAIProvider: TypeAlias = Literal["claude", "codex"]
AIProviderEnv: TypeAlias = ClaudeEnvironment | CodexEnvironment

AI_PROVIDER_ENV_VAR = "SYNAPSE_AI_PROVIDER"
DEFAULT_PROVIDER: ConcreteAIProvider = "codex"


class AIError(RuntimeError):
    """Provider-agnostic AI call failure."""


class AIUnavailableError(AIError):
    """Selected AI provider is unavailable."""


class CompleteCallable(Protocol):
    def __call__(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
        timeout: int = 120,
        env: Any = None,
    ) -> str: ...


class StructuredCallable(Protocol):
    def __call__(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
        timeout: int = 120,
        env: Any = None,
    ) -> Any: ...


@dataclass(frozen=True)
class AIProviderAdapter:
    default_model: str
    detect_environment: Callable[[str], object]
    complete: CompleteCallable
    complete_structured: StructuredCallable
    model_of: Callable[[object], str]
    path_of: Callable[[object], str | None]
    version_of: Callable[[object], str | None]
    ready_of: Callable[[object], bool]
    reasons_unavailable_of: Callable[[object], list[str]]
    unavailable_errors: tuple[type[Exception], ...]
    provider_errors: tuple[type[Exception], ...]


@dataclass(frozen=True)
class AIEnvironment:
    provider: ConcreteAIProvider
    provider_env: object

    @property
    def model(self) -> str:
        return PROVIDERS[self.provider].model_of(self.provider_env)

    @property
    def path(self) -> str | None:
        return PROVIDERS[self.provider].path_of(self.provider_env)

    @property
    def version(self) -> str | None:
        return PROVIDERS[self.provider].version_of(self.provider_env)

    @property
    def ready(self) -> bool:
        return PROVIDERS[self.provider].ready_of(self.provider_env)

    def reasons_unavailable(self) -> list[str]:
        return PROVIDERS[self.provider].reasons_unavailable_of(self.provider_env)


def _complete_claude(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 120,
    env: Any = None,
) -> str:
    return claude.complete(
        prompt,
        system=system,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
    )


def _complete_structured_claude(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 120,
    env: Any = None,
) -> Any:
    return claude.complete_structured(
        prompt,
        system=system,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
    )


def _complete_codex(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 120,
    env: Any = None,
) -> str:
    return codex.complete(
        prompt,
        system=system,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
    )


def _complete_structured_codex(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 120,
    env: Any = None,
) -> Any:
    return codex.complete_structured(
        prompt,
        system=system,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
    )


def _as_claude_environment(env: object) -> ClaudeEnvironment:
    if isinstance(env, ClaudeEnvironment):
        return env
    raise AIUnavailableError("Claude provider requested with non-Claude environment")


def _as_codex_environment(env: object) -> CodexEnvironment:
    if isinstance(env, CodexEnvironment):
        return env
    raise AIUnavailableError("Codex provider requested with non-Codex environment")


PROVIDERS: dict[ConcreteAIProvider, AIProviderAdapter] = {
    "claude": AIProviderAdapter(
        default_model=claude.DEFAULT_MODEL,
        detect_environment=claude.detect_claude_environment,
        complete=_complete_claude,
        complete_structured=_complete_structured_claude,
        model_of=lambda env: _as_claude_environment(env).model,
        path_of=lambda env: _as_claude_environment(env).claude_path,
        version_of=lambda env: _as_claude_environment(env).claude_version,
        ready_of=lambda env: _as_claude_environment(env).ready,
        reasons_unavailable_of=lambda env: _as_claude_environment(
            env
        ).reasons_unavailable(),
        unavailable_errors=(claude.ClaudeUnavailableError,),
        provider_errors=(claude.ClaudeError,),
    ),
    "codex": AIProviderAdapter(
        default_model=codex.DEFAULT_MODEL,
        detect_environment=codex.detect_codex_environment,
        complete=_complete_codex,
        complete_structured=_complete_structured_codex,
        model_of=lambda env: _as_codex_environment(env).model,
        path_of=lambda env: _as_codex_environment(env).codex_path,
        version_of=lambda env: _as_codex_environment(env).codex_version,
        ready_of=lambda env: _as_codex_environment(env).ready,
        reasons_unavailable_of=lambda env: _as_codex_environment(
            env
        ).reasons_unavailable(),
        unavailable_errors=(codex.CodexUnavailableError,),
        provider_errors=(codex.CodexError,),
    ),
}


def detect_ai_environment(
    provider: AIProvider | None = None,
    *,
    model: str | None = None,
) -> AIEnvironment:
    resolved = _resolve_provider(provider)
    adapter = PROVIDERS[resolved]
    return AIEnvironment(
        provider=resolved,
        provider_env=adapter.detect_environment(model or adapter.default_model),
    )


def complete(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 120,
    env: AIEnvironment | AIProviderEnv | None = None,
    provider: AIProvider | None = None,
) -> str:
    resolved = _coerce_env(env, provider=provider, model=model)
    adapter = PROVIDERS[resolved.provider]
    try:
        return adapter.complete(
            prompt,
            system=system,
            model=model,
            json_schema=json_schema,
            max_budget_usd=max_budget_usd,
            timeout=timeout,
            env=resolved.provider_env,
        )
    except Exception as exc:
        _raise_provider_error(exc, adapter)


def complete_structured(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 120,
    env: AIEnvironment | AIProviderEnv | None = None,
    provider: AIProvider | None = None,
) -> Any:
    resolved = _coerce_env(env, provider=provider, model=model)
    adapter = PROVIDERS[resolved.provider]
    try:
        return adapter.complete_structured(
            prompt,
            system=system,
            model=model,
            json_schema=json_schema,
            max_budget_usd=max_budget_usd,
            timeout=timeout,
            env=resolved.provider_env,
        )
    except Exception as exc:
        _raise_provider_error(exc, adapter)


def _coerce_env(
    env: AIEnvironment | AIProviderEnv | None,
    *,
    provider: AIProvider | None,
    model: str | None,
) -> AIEnvironment:
    if isinstance(env, AIEnvironment):
        return env
    if isinstance(env, ClaudeEnvironment):
        return AIEnvironment(provider="claude", provider_env=env)
    if isinstance(env, CodexEnvironment):
        return AIEnvironment(provider="codex", provider_env=env)
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


def _raise_provider_error(exc: Exception, adapter: AIProviderAdapter) -> NoReturn:
    if isinstance(exc, adapter.unavailable_errors):
        raise AIUnavailableError(str(exc)) from exc
    if isinstance(exc, adapter.provider_errors):
        raise AIError(str(exc)) from exc
    raise exc
