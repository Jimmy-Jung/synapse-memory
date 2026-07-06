"""Claude Code CLI wrapper — Anthropic API SDK 대신 ``claude`` 명령 subprocess.

CLI subprocess 패턴. API key 별도 발급 불필요 — 사용자 Claude Code
OAuth 인증 그대로 사용.

**철칙 1**: D4 — raw 텍스트를 그대로 cloud claude CLI에 전달한다.
**철칙 2**: 비용 절감 — ``--system-prompt``로 default system prompt 대체.
   default 사용 시 CLAUDE.md/memory/plugins가 자동 합쳐져 35K+ cache 만들어짐 ($0.24/call).
   ``--system-prompt`` 명시하면 dynamic sections 자동 제외 → ~$0.001/call.

NOTE: ``--bare`` 모드는 OAuth/keychain 인증을 무시하고 ANTHROPIC_API_KEY만 받음.
사용자가 Pro/Max 구독으로 OAuth 인증한 경우 사용 불가 → bare 안 씀.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Literal, cast

from synapse_memory.cost.events import CostStatus, append_cost_event
from synapse_memory.llm._runtime import (
    DEFAULT_STRUCTURED_SYSTEM,
    CompleteOptions,
    detect_cli_environment,
    make_structured_call,
    make_text_call,
    model_from_cmd,
    model_from_envelope,
    parse_structured_text,
    record_llm_cost,
    run_cli_process,
    with_system,
)

CLAUDE_BIN = "claude"
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SEC = 60


def _known_claude_paths() -> tuple[str, ...]:
    return (
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
    )


class ClaudeError(RuntimeError):
    """Claude CLI 호출 실패."""


class ClaudeUnavailableError(ClaudeError):
    """Claude Code CLI 미설치 또는 미인증."""


@dataclass(frozen=True)
class ClaudeEnvironment:
    claude_path: str | None
    claude_version: str | None
    model: str = DEFAULT_MODEL

    @property
    def provider(self) -> Literal["claude"]:
        return "claude"

    @property
    def path(self) -> str | None:
        return self.claude_path

    @property
    def version(self) -> str | None:
        return self.claude_version

    @property
    def ready(self) -> bool:
        return self.claude_path is not None

    def reasons_unavailable(self) -> list[str]:
        if not self.claude_path:
            return [
                "Claude Code CLI 미설치 — 설치: https://docs.claude.com/claude-code"
            ]
        return []


def detect_claude_environment(model: str = DEFAULT_MODEL) -> ClaudeEnvironment:
    return detect_cli_environment(
        bin_name=CLAUDE_BIN,
        model=model,
        make_env=_make_claude_environment,
        which=shutil.which,
        run=subprocess.run,
        known_paths=_known_claude_paths(),
        is_file=os.path.isfile,
        is_executable=os.access,
    )


def _make_claude_environment(
    path: str | None,
    version: str | None,
    model: str,
) -> ClaudeEnvironment:
    return ClaudeEnvironment(claude_path=path, claude_version=version, model=model)


def _ensure_ready(env: ClaudeEnvironment) -> None:
    if not env.ready:
        raise ClaudeUnavailableError(" / ".join(env.reasons_unavailable()))


_MINIMAL_SYSTEM_FALLBACK = "You are a concise assistant."


def _build_cmd(
    env: ClaudeEnvironment,
    *,
    system: str | None,
    model: str | None,
    json_schema: dict[str, Any] | None,
    max_budget_usd: float | None,
) -> list[str]:
    """공통 옵션 — non-interactive + json envelope + system-prompt 강제.

    ``--system-prompt`` 항상 설정 — 사용자 CLAUDE.md/memory/plugins/dynamic sections이
    cache로 들어가는 것 방지 (cache_creation 35K → 0).

    ``--setting-sources ""`` — user/project/local settings 전부 미로드. 사용자
    SessionStart hook(예: caveman plugin)이 이 subprocess에 주입돼 사서 응답을
    JSON 대신 압축 텍스트로 오염시키는 것 방지. ``--bare``와 달리 OAuth/keychain
    인증은 그대로 유지. ``--strict-mcp-config`` — MCP 서버 미로드(사서는 tool 불필요).
    ``--exclude-dynamic-system-prompt-sections`` — system-prompt 명시와 함께 동적
    섹션 제거로 cache 추가 절감.

    ``--settings '{"verbose":false}'`` — 사용자 전역 ``~/.claude.json``의
    ``verbose:true``를 inline override. verbose가 켜져 있으면 ``--output-format json``이
    단일 result 객체 대신 stream-json 배열을 내보내 envelope 파싱이 깨진다.
    ``--setting-sources ""``는 user/project/local settings만 차단할 뿐 ``~/.claude.json``은
    덮지 못하므로 별도 override가 필요하다.
    """
    assert env.claude_path is not None
    cmd: list[str] = [
        env.claude_path,
        "--print",
        "--output-format", "json",
        "--no-session-persistence",
        "--permission-mode", "bypassPermissions",  # tool 안 씀, 권한 묻기 skip
        # settings 미로드 → user/project hook·plugin(caveman 등) 주입 차단.
        # OAuth/keychain 인증은 setting-sources와 무관하게 유지됨.
        "--setting-sources", "",
        "--strict-mcp-config",  # MCP 서버 미로드 (사서는 tool 안 씀)
        "--exclude-dynamic-system-prompt-sections",  # cache 추가 절감
        # ~/.claude.json verbose:true inline override — verbose면 --output-format
        # json이 stream-json 배열을 내보내 envelope 파싱이 깨진다 (setting-sources로
        # 차단 안 됨). 단일 result 객체 보장.
        "--settings", '{"verbose":false}',
        "--model", model or env.model,
        # 항상 system-prompt 명시 (없으면 minimal fallback) — default 시스템 prompt 회피
        "--system-prompt", system or _MINIMAL_SYSTEM_FALLBACK,
    ]
    if json_schema is not None:
        cmd.extend(["--json-schema", json.dumps(json_schema, ensure_ascii=False)])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    return cmd


def _run_claude(
    cmd: list[str],
    *,
    prompt: str,
    timeout: int,
) -> dict[str, Any]:
    """subprocess + envelope JSON 파싱. envelope dict 반환."""
    model = model_from_cmd(cmd, default=DEFAULT_MODEL)
    result, elapsed = run_cli_process(
        command_name="claude",
        cmd=[*cmd, prompt],
        timeout=timeout,
        run=subprocess.run,
        error_cls=ClaudeError,
        prompt_for_cost=prompt,
        model=model,
        record=_record_cost,
    )

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        _record_cost(
            model=model,
            prompt=prompt,
            result_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="invalid_envelope_json",
        )
        raise ClaudeError(
            f"envelope JSON 파싱 실패: {result.stdout[:200]!r}"
        ) from exc

    normalized = _normalize_envelope(envelope)

    if normalized.get("is_error"):
        _record_cost(
            model=model_from_envelope(normalized, fallback=model),
            prompt=prompt,
            result_text=str(normalized.get("result") or ""),
            status="error",
            elapsed_s=elapsed,
            envelope=normalized,
            error_kind=str(normalized.get("subtype") or "envelope_error"),
        )
        msg = normalized.get("result") or normalized.get("subtype") or "unknown"
        raise ClaudeError(f"Claude 응답 에러: {msg}")

    _record_cost(
        model=model_from_envelope(normalized, fallback=model),
        prompt=prompt,
        result_text=str(normalized.get("result") or ""),
        status="success",
        elapsed_s=elapsed,
        envelope=normalized,
    )
    return normalized


def _record_cost(
    *,
    model: str,
    prompt: str,
    result_text: str,
    status: CostStatus,
    elapsed_s: float,
    envelope: dict[str, Any] | None = None,
    error_kind: str | None = None,
) -> None:
    record_llm_cost(
        provider="claude",
        model=model,
        prompt=prompt,
        result_text=result_text,
        status=status,
        elapsed_s=elapsed_s,
        envelope=envelope,
        error_kind=error_kind,
        append=append_cost_event,
    )


def _normalize_envelope(envelope: Any) -> dict[str, Any]:
    """Claude Code JSON output variants → final result envelope.

    Claude Code 2.1+ can return a JSON event array for ``--output-format json``.
    The final event with ``type == "result"`` contains the same result fields
    that older single-dict output exposed directly.
    """
    if isinstance(envelope, dict):
        return cast(dict[str, Any], envelope)

    if isinstance(envelope, list):
        for event in reversed(envelope):
            if isinstance(event, dict) and event.get("type") == "result":
                return event
        raise ClaudeError("Claude event stream에 result event 없음")

    raise ClaudeError(f"envelope이 dict/list 아님: {type(envelope).__name__}")


def _complete_envelope(
    prompt: str,
    *,
    options: CompleteOptions,
) -> dict[str, Any]:
    """공통 준비(env 진단 + cmd 빌드) + CLI 호출 → normalized envelope dict.

    ``complete``(텍스트)와 ``complete_structured``(structured_output) 양쪽이
    동일 호출 경로를 공유하도록 추출.
    """
    env = cast(ClaudeEnvironment | None, options.env)
    env = env or detect_claude_environment(options.model or DEFAULT_MODEL)
    _ensure_ready(env)
    cmd = _build_cmd(
        env,
        system=options.system,
        model=options.model,
        json_schema=options.json_schema,
        max_budget_usd=options.max_budget_usd,
    )
    return _run_claude(cmd, prompt=prompt, timeout=options.timeout)


def _complete_text(prompt: str, options: CompleteOptions) -> str:
    """Claude Code CLI 단일 호출 → 응답 텍스트."""
    envelope = _complete_envelope(prompt, options=options)
    content = envelope.get("result", "")
    if not isinstance(content, str):
        raise ClaudeError(
            f"envelope.result가 string 아님: {type(content).__name__}"
        )
    return content


def _complete_structured(prompt: str, options: CompleteOptions) -> Any:
    """JSON 응답 → parse. ``json_schema`` 명시 시 Claude가 직접 검증.

    Raises:
        ClaudeError: 호출 실패 또는 JSON 추출 실패.
    """
    envelope = _complete_envelope(
        prompt,
        options=with_system(options, options.system or DEFAULT_STRUCTURED_SYSTEM),
    )
    # json_schema 명시 시 CLI가 schema-검증한 객체를 ``structured_output``에 채운다.
    # 모델이 ``result``에 산문으로 답해도(긴/모호한 프롬프트에서 발생) 검증된
    # structured_output을 우선 사용 — 파싱 실패 없이 dict 반환.
    structured = envelope.get("structured_output")
    if structured is not None:
        return structured
    content = envelope.get("result", "")
    if not isinstance(content, str):
        raise ClaudeError(
            f"envelope.result가 string 아님: {type(content).__name__}"
        )
    return _parse_json_with_fallback(content)


def _parse_json_with_fallback(content: str) -> Any:
    return parse_structured_text(content, error_cls=ClaudeError, provider="Claude")


complete = make_text_call(_complete_text, default_timeout=DEFAULT_TIMEOUT_SEC)
complete_structured = make_structured_call(
    _complete_structured,
    default_timeout=DEFAULT_TIMEOUT_SEC,
)
ProviderError = ClaudeError
ProviderUnavailableError = ClaudeUnavailableError
detect_environment = detect_claude_environment
