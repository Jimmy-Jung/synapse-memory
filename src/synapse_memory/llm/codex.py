"""Codex CLI wrapper for AI-agent runtime calls."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse_memory.cost.events import append_cost_event, build_cost_event
from synapse_memory.cost.pricing import price_usage
from synapse_memory.llm._json import parse_json_with_fallback as _parse_json_base
from synapse_memory.llm.tokens import estimate_tokens

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
    def ready(self) -> bool:
        return self.codex_path is not None

    def reasons_unavailable(self) -> list[str]:
        if not self.codex_path:
            return ["Codex CLI 미설치 — `codex --version` 확인 필요"]
        return []


def detect_codex_environment(model: str = DEFAULT_MODEL) -> CodexEnvironment:
    path = shutil.which(CODEX_BIN)
    version = None
    if path:
        try:
            r = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if r.returncode == 0:
                version = r.stdout.strip() or r.stderr.strip() or None
        except (subprocess.TimeoutExpired, OSError):
            pass
    return CodexEnvironment(codex_path=path, codex_version=version, model=model)


def _ensure_ready(env: CodexEnvironment) -> None:
    if not env.ready:
        raise CodexUnavailableError(" / ".join(env.reasons_unavailable()))


def complete(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: CodexEnvironment | None = None,
) -> str:
    """Codex CLI non-interactive call → final answer text."""
    _ = max_budget_usd  # Codex CLI has no compatible per-call budget flag here.
    env = env or detect_codex_environment(model or DEFAULT_MODEL)
    _ensure_ready(env)
    assert env.codex_path is not None

    started = time.monotonic()
    full_prompt = _compose_prompt(prompt=prompt, system=system)
    with tempfile.TemporaryDirectory(prefix="synapse-codex-") as tmp:
        out_path = Path(tmp) / "last-message.txt"
        schema_path = _write_schema(tmp, json_schema)
        cmd = _build_cmd(
            env,
            model=model,
            output_path=out_path,
            schema_path=schema_path,
        )
        try:
            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            _record_codex_cost(
                model=model or env.model,
                prompt=full_prompt,
                result_text="",
                status="timeout",
                elapsed_s=elapsed,
                error_kind="timeout",
            )
            raise CodexError(f"codex 호출 타임아웃 ({timeout}s)") from exc
        except OSError as exc:
            elapsed = time.monotonic() - started
            _record_codex_cost(
                model=model or env.model,
                prompt=full_prompt,
                result_text="",
                status="error",
                elapsed_s=elapsed,
                error_kind="os_error",
            )
            raise CodexError(f"codex 실행 실패: {exc}") from exc

        elapsed = time.monotonic() - started
        if result.returncode != 0:
            _record_codex_cost(
                model=model or env.model,
                prompt=full_prompt,
                result_text="",
                status="error",
                elapsed_s=elapsed,
                error_kind="nonzero_exit",
            )
            msg = result.stderr.strip() or result.stdout.strip()[:500] or "(no output)"
            raise CodexError(f"codex 비정상 종료 exit={result.returncode}: {msg}")

        text = _read_last_message(out_path, result.stdout)
        _record_codex_cost(
            model=model or env.model,
            prompt=full_prompt,
            result_text=text,
            status="success",
            elapsed_s=elapsed,
        )
        return text


def complete_structured(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: CodexEnvironment | None = None,
) -> Any:
    text = complete(
        prompt,
        system=system or _DEFAULT_STRUCTURED_SYSTEM,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
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


def _compose_prompt(*, prompt: str, system: str | None) -> str:
    if not system:
        return prompt
    return f"# System\n{system}\n\n# User\n{prompt}"


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


def _record_codex_cost(
    *,
    model: str,
    prompt: str,
    result_text: str,
    status: str,
    elapsed_s: float,
    error_kind: str | None = None,
) -> None:
    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(result_text)
    priced = price_usage(
        provider="codex",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    try:
        append_cost_event(
            build_cost_event(
                provider="codex",
                model=model,
                status=status,  # type: ignore[arg-type]
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


_DEFAULT_STRUCTURED_SYSTEM = (
    "You output ONLY a single valid JSON value. "
    "No prose, no markdown code fences, no explanation."
)


def _parse_json_with_fallback(content: str) -> Any:
    return _parse_json_base(content, error_cls=CodexError, provider="Codex")
