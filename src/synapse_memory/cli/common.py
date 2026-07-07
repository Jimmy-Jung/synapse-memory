"""Shared CLI helpers kept light for hook startup."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

OK = "✓"
FAIL = "✗"

_INTERACTIVE_GUARD_DELAY_SECONDS = 3
_INTERACTIVE_GUARD_MESSAGE = (
    "⚠  {command} 는 LLM 대화 컨텍스트에서 호출할 때 가장 자연스럽게 동작합니다.\n"
    "   Claude Code / Codex 안에서 `/sm:{slash}` 슬래시 명령으로 호출하면\n"
    "   결과가 대화에 인라인되고 후속 질문에 컨텍스트가 유지됩니다.\n"
    "   계속 진행하려면 {delay}초 기다리세요. 즉시 우회: SYNAPSE_FROM_AGENT=1\n"
)


def api() -> Any:
    return sys.modules["synapse_memory.cli"]


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _interactive_guard(command: str, slash: str) -> None:
    if os.environ.get("SYNAPSE_FROM_AGENT"):
        return
    if not api()._stdout_is_tty():
        return
    try:
        from synapse_memory.config import get_config

        cfg = get_config()
        if not cfg.interactive_guard.enabled:
            return
        delay = cfg.interactive_guard.delay_seconds
    except Exception:
        delay = _INTERACTIVE_GUARD_DELAY_SECONDS
    sys.stderr.write(
        _INTERACTIVE_GUARD_MESSAGE.format(command=command, slash=slash, delay=delay)
    )
    sys.stderr.flush()
    api().time.sleep(delay)


def _arg_or_config(arg_value: Any, cfg_path: str, fallback: Any = None) -> Any:
    if arg_value is not None:
        return arg_value
    try:
        from synapse_memory.config import get_config, get_value

        return get_value(get_config(), cfg_path)
    except (KeyError, Exception):
        return fallback


def _enforce_cost_cap(command: str) -> None:
    try:
        from synapse_memory.cost.cap import enforce_cost_cap

        enforce_cost_cap(command)
    except SystemExit:
        raise
    except Exception:
        pass


def _resolve_model(arg_model: str | None, task: str) -> str | None:
    if arg_model is not None:
        return arg_model
    try:
        from synapse_memory.config import get_config

        cfg = get_config()
        # 모델은 '스폰되는 provider'(config) 기준으로 해석한다. runtime 감지
        # (Claude Code/Codex 세션 내부 여부)는 config가 auto일 때만 참고 —
        # 그렇지 않으면 Claude Code 안에서 codex를 스폰할 때 claude용 모델
        # (sonnet)이 codex에 전달되는 불일치가 생긴다.
        provider = os.environ.get("SYNAPSE_AI_PROVIDER") or cfg.ai_provider
        if provider == "auto":
            provider = _runtime_ai_provider() or "auto"
        if provider == "auto":
            return None
        model_for_task = getattr(cfg.models, "model_for_task", None)
        if callable(model_for_task):
            return model_for_task(provider, task)
        provider_models = getattr(cfg.models, provider, None)
        if provider_models is None:
            return None
        return getattr(provider_models, task, None)
    except Exception:
        return None


def _runtime_ai_provider() -> str | None:
    if any(
        os.environ.get(name)
        for name in (
            "CODEX_CI",
            "CODEX_THREAD_ID",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        )
    ):
        return "codex"
    if any(
        os.environ.get(name)
        for name in (
            "CLAUDECODE",
            "CLAUDE_CODE",
            "CLAUDE_PROJECT_DIR",
        )
    ):
        return "claude"
    return None


def _resolve_vault(
    args: argparse.Namespace | None = None, *, require_exists: bool = False
) -> Path:
    raw = None
    if args is not None:
        raw = getattr(args, "vault", None) or getattr(args, "vault_path", None)
    vault = Path(raw).expanduser().resolve() if raw else api().get_vault_path()
    if require_exists and not vault.is_dir():
        print(f"{FAIL} vault 경로가 존재하지 않습니다: {vault}", file=sys.stderr)
        raise SystemExit(2)
    return vault


def _command_name(args: argparse.Namespace) -> str:
    cmd = str(getattr(args, "cmd", "unknown") or "unknown")
    parts = [cmd]
    for attr in ("source", "kind", "action", "feedback_target"):
        value = getattr(args, attr, None)
        if isinstance(value, str) and value:
            parts.append(value.replace("-", "_"))
    return ".".join(parts)
