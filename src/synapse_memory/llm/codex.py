"""Codex CLI wrapper for AI-agent runtime calls."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from synapse_memory.cost.events import CostStatus, append_cost_event
from synapse_memory.llm._runtime import (
    DEFAULT_STRUCTURED_SYSTEM,
    CompleteOptions,
    compose_prompt,
    detect_cli_environment,
    make_structured_call,
    make_text_call,
    parse_structured_text,
    record_llm_cost,
    run_cli_process,
    with_system,
)

CODEX_BIN = "codex"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TIMEOUT_SEC = 240


class CodexError(RuntimeError):
    """Codex CLI 호출 실패."""


class CodexUnavailableError(CodexError):
    """Codex CLI 미설치 또는 미인증."""


@dataclass(frozen=True)
class CodexEnvironment:
    codex_path: str | None
    codex_version: str | None
    model: str = DEFAULT_MODEL

    @property
    def provider(self) -> Literal["codex"]:
        return "codex"

    @property
    def path(self) -> str | None:
        return self.codex_path

    @property
    def version(self) -> str | None:
        return self.codex_version

    @property
    def ready(self) -> bool:
        return self.codex_path is not None

    def reasons_unavailable(self) -> list[str]:
        if not self.codex_path:
            return ["Codex CLI 미설치 — `codex --version` 확인 필요"]
        return []


def detect_codex_environment(model: str = DEFAULT_MODEL) -> CodexEnvironment:
    return detect_cli_environment(
        bin_name=CODEX_BIN,
        model=model,
        make_env=_make_codex_environment,
        which=shutil.which,
        run=subprocess.run,
    )


def _make_codex_environment(
    path: str | None,
    version: str | None,
    model: str,
) -> CodexEnvironment:
    return CodexEnvironment(codex_path=path, codex_version=version, model=model)


def _ensure_ready(env: CodexEnvironment) -> None:
    if not env.ready:
        raise CodexUnavailableError(" / ".join(env.reasons_unavailable()))


def _complete_text(prompt: str, options: CompleteOptions) -> str:
    """Codex CLI non-interactive call → final answer text."""
    _ = options.max_budget_usd  # Codex CLI has no compatible per-call budget flag here.
    env = cast(CodexEnvironment | None, options.env)
    env = env or detect_codex_environment(options.model or DEFAULT_MODEL)
    _ensure_ready(env)
    assert env.codex_path is not None

    full_prompt = compose_prompt(prompt=prompt, system=options.system)
    with tempfile.TemporaryDirectory(prefix="synapse-codex-") as tmp:
        out_path = Path(tmp) / "last-message.txt"
        schema_path = _write_schema(tmp, options.json_schema)
        cmd = _build_cmd(
            env,
            model=options.model,
            output_path=out_path,
            schema_path=schema_path,
        )
        result, elapsed = run_cli_process(
            command_name="codex",
            cmd=cmd,
            input_text=full_prompt,
            timeout=options.timeout,
            run=subprocess.run,
            error_cls=CodexError,
            prompt_for_cost=full_prompt,
            model=options.model or env.model,
            record=_record_cost,
        )

        text = _read_last_message(out_path, result.stdout)
        _record_cost(
            model=options.model or env.model,
            prompt=full_prompt,
            result_text=text,
            status="success",
            elapsed_s=elapsed,
        )
        return text


def _complete_structured(prompt: str, options: CompleteOptions) -> Any:
    text = _complete_text(
        prompt,
        with_system(options, options.system or DEFAULT_STRUCTURED_SYSTEM),
    )
    return _parse_json_with_fallback(text)


def _build_cmd(
    env: CodexEnvironment,
    *,
    model: str | None,
    output_path: Path,
    schema_path: Path | None,
) -> list[str]:
    assert env.codex_path is not None
    cmd = [
        env.codex_path,
        "exec",
        "--color",
        "never",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--skip-git-repo-check",
        # 사용자 ~/.codex/config.toml + rules/skill 미로드 — 사서 subprocess가
        # 사용자 skill 로드 실패("failed to load skill")로 죽는 것 방지. auth는 유지.
        "--ignore-user-config",
        "--ignore-rules",
        "--output-last-message",
        str(output_path),
        "-m",
        model or env.model,
    ]
    if schema_path is not None:
        cmd.extend(["--output-schema", str(schema_path)])
    cmd.append("-")
    return cmd


def _normalize_schema_for_codex(node: Any) -> Any:
    """JSON schema를 OpenAI structured output strict 규격으로 정규화.

    codex ``--output-schema``는 OpenAI strict 규격을 강제한다(미준수 시 exit=1):
    모든 object에 ``additionalProperties: false``, ``required``에 전체 property 키.
    claude ``--json-schema``는 관대해 INTEGRATION_SCHEMA가 그대로 통과하지만
    codex는 거부하므로 codex 경로에서만 변환한다.
    """
    if isinstance(node, dict):
        out = {k: _normalize_schema_for_codex(v) for k, v in node.items()}
        if out.get("type") == "object" and isinstance(out.get("properties"), dict):
            out["additionalProperties"] = False
            out["required"] = list(out["properties"].keys())
        return out
    if isinstance(node, list):
        return [_normalize_schema_for_codex(x) for x in node]
    return node


def _write_schema(tmp: str, schema: dict[str, Any] | None) -> Path | None:
    if schema is None:
        return None
    path = Path(tmp) / "schema.json"
    normalized = _normalize_schema_for_codex(schema)
    path.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
    return path


def _read_last_message(path: Path, stdout: str) -> str:
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return stdout.strip()


def _record_cost(
    *,
    model: str,
    prompt: str,
    result_text: str,
    status: CostStatus,
    elapsed_s: float,
    error_kind: str | None = None,
) -> None:
    record_llm_cost(
        provider="codex",
        model=model,
        prompt=prompt,
        result_text=result_text,
        status=status,
        elapsed_s=elapsed_s,
        error_kind=error_kind,
        append=append_cost_event,
    )


def _parse_json_with_fallback(content: str) -> Any:
    return parse_structured_text(content, error_cls=CodexError, provider="Codex")


complete = make_text_call(_complete_text, default_timeout=DEFAULT_TIMEOUT_SEC)
complete_structured = make_structured_call(
    _complete_structured,
    default_timeout=DEFAULT_TIMEOUT_SEC,
)
ProviderError = CodexError
ProviderUnavailableError = CodexUnavailableError
detect_environment = detect_codex_environment
