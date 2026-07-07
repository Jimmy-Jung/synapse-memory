"""Shared runtime helpers for concrete LLM CLI adapters.

저자: JunyoungJung
작성일: 2026-07-06
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from typing import Any, Literal, Protocol, TypeAlias, TypeVar, cast

from synapse_memory.cost.events import (
    CostEvent,
    CostProvider,
    CostStatus,
    append_cost_event,
    build_cost_event,
)
from synapse_memory.cost.pricing import price_usage
from synapse_memory.llm._json import parse_json_with_fallback as _parse_json_base
from synapse_memory.llm.tokens import estimate_tokens

ConcreteProvider: TypeAlias = Literal["claude", "codex"]

DEFAULT_STRUCTURED_SYSTEM = (
    "You output ONLY a single valid JSON value. "
    "No prose, no markdown code fences, no explanation. "
    "Korean text inside JSON string values is OK."
)


class ProviderEnvironment(Protocol):
    provider: ConcreteProvider
    model: str
    ready: bool
    path: str | None
    version: str | None

    def reasons_unavailable(self) -> list[str]: ...


class ProviderModule(Protocol):
    DEFAULT_MODEL: str
    ProviderError: type[Exception]
    ProviderUnavailableError: type[Exception]

    def detect_environment(self, model: str) -> ProviderEnvironment: ...

    def complete(self, prompt: str, **kwargs: Any) -> str: ...

    def complete_structured(self, prompt: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class CompleteOptions:
    system: str | None = None
    model: str | None = None
    json_schema: dict[str, Any] | None = None
    max_budget_usd: float | None = None
    timeout: int = 120
    env: Any = None


_OPTION_KEYS = frozenset(field.name for field in fields(CompleteOptions))


def with_system(options: CompleteOptions, system: str | None) -> CompleteOptions:
    return replace(options, system=system)


def with_env(options: CompleteOptions, env: Any) -> CompleteOptions:
    return replace(options, env=env)


def options_kwargs(options: CompleteOptions) -> dict[str, Any]:
    return {field.name: getattr(options, field.name) for field in fields(options)}


def make_options(*, default_timeout: int, kwargs: dict[str, Any]) -> CompleteOptions:
    unknown = sorted(set(kwargs) - _OPTION_KEYS)
    if unknown:
        names = ", ".join(unknown)
        raise TypeError(f"unexpected complete option(s): {names}")
    data: dict[str, Any] = {key: kwargs.get(key) for key in _OPTION_KEYS}
    data["timeout"] = kwargs.get("timeout", default_timeout)
    return CompleteOptions(**data)


Runner = Callable[[str, CompleteOptions], Any]


def make_text_call(runner: Runner, *, default_timeout: int) -> Callable[..., str]:
    def call(prompt: str, **kwargs: Any) -> str:
        return cast(str, runner(prompt, make_options(default_timeout=default_timeout, kwargs=kwargs)))

    call.__name__ = "complete"
    return call


def make_structured_call(runner: Runner, *, default_timeout: int) -> Callable[..., Any]:
    def call(prompt: str, **kwargs: Any) -> Any:
        return runner(prompt, make_options(default_timeout=default_timeout, kwargs=kwargs))

    call.__name__ = "complete_structured"
    return call


EnvT = TypeVar("EnvT")


def detect_cli_environment(*, bin_name: str, model: str, make_env: Callable[[str | None, str | None, str], EnvT], which: Callable[[str], str | None], run: Callable[..., subprocess.CompletedProcess[str]], known_paths: tuple[str, ...] = (), is_file: Callable[[str], bool] = os.path.isfile, is_executable: Callable[[str, int], bool] = os.access) -> EnvT:
    path = which(bin_name) or _first_executable(
        known_paths,
        is_file=is_file,
        is_executable=is_executable,
    )
    version = None
    if path:
        try:
            result = run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip() or None
        except (subprocess.TimeoutExpired, OSError):
            pass
    return make_env(path, version, model)


def _first_executable(candidates: tuple[str, ...], *, is_file: Callable[[str], bool], is_executable: Callable[[str, int], bool]) -> str | None:
    return next((c for c in candidates if is_file(c) and is_executable(c, os.X_OK)), None)


Recorder = Callable[..., None]


def run_cli_process(*, command_name: str, cmd: list[str], timeout: int, run: Callable[..., subprocess.CompletedProcess[str]], error_cls: type[Exception], prompt_for_cost: str, model: str, record: Recorder, input_text: str | None = None) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.monotonic()
    try:
        result = run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        record(
            model=model,
            prompt=prompt_for_cost,
            result_text="",
            status="timeout",
            elapsed_s=elapsed,
            error_kind="timeout",
        )
        raise error_cls(f"{command_name} 호출 타임아웃 ({timeout}s)") from exc
    except OSError as exc:
        elapsed = time.monotonic() - started
        record(
            model=model,
            prompt=prompt_for_cost,
            result_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="os_error",
        )
        raise error_cls(f"{command_name} 실행 실패: {exc}") from exc

    elapsed = time.monotonic() - started
    if result.returncode != 0:
        record(
            model=model,
            prompt=prompt_for_cost,
            result_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="nonzero_exit",
        )
        msg = result.stderr.strip() or result.stdout.strip()[:500] or "(no output)"
        raise error_cls(f"{command_name} 비정상 종료 exit={result.returncode}: {msg}")

    return result, elapsed


def record_llm_cost(*, provider: CostProvider, model: str, prompt: str, result_text: str, status: CostStatus, elapsed_s: float, envelope: dict[str, Any] | None = None, error_kind: str | None = None, append: Callable[[CostEvent], object] = append_cost_event) -> None:
    envelope = envelope or {}
    input_tokens, output_tokens = _usage_from_envelope(envelope)
    if input_tokens == 0:
        input_tokens = estimate_tokens(prompt)
    if output_tokens == 0 and result_text:
        output_tokens = estimate_tokens(result_text)
    priced = price_usage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        provider_usd=_usd_from_envelope(envelope),
    )
    try:
        append(
            build_cost_event(
                provider=provider,
                model=model,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usd=priced.usd,
                pricing_source=priced.pricing_source,
                elapsed_s=elapsed_s,
                error_kind=error_kind,
            )
        )
    except Exception as exc:
        print(f"⚠ cost event 기록 실패: {exc}", file=sys.stderr)


def parse_structured_text(content: str, *, error_cls: type[Exception], provider: str) -> Any:
    return _parse_json_base(content, error_cls=error_cls, provider=provider)


def compose_prompt(*, prompt: str, system: str | None) -> str:
    if not system:
        return prompt
    return f"# System\n{system}\n\n# User\n{prompt}"


def model_from_cmd(cmd: list[str], *, default: str) -> str:
    if "--model" in cmd:
        idx = cmd.index("--model")
        if idx + 1 < len(cmd):
            return cmd[idx + 1]
    return default


def model_from_envelope(envelope: dict[str, Any], *, fallback: str) -> str:
    raw = envelope.get("model") or envelope.get("model_id")
    return str(raw) if raw else fallback


def _usage_from_envelope(envelope: dict[str, Any]) -> tuple[int, int]:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    return (
        _first_int(envelope, usage, keys=("input_tokens", "prompt_tokens")),
        _first_int(envelope, usage, keys=("output_tokens", "completion_tokens")),
    )


def _first_int(*sources: dict[str, Any], keys: tuple[str, ...]) -> int:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return max(0, value)
            if isinstance(value, float) and value.is_integer():
                return max(0, int(value))
    return 0


def _usd_from_envelope(envelope: dict[str, Any]) -> float | None:
    for key in ("total_cost_usd", "cost_usd", "usd"):
        value = envelope.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None
