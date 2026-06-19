"""Claude Code CLI wrapper — Anthropic API SDK 대신 ``claude`` 명령 subprocess.

CLI subprocess 패턴. API key 별도 발급 불필요 — 사용자 Claude Code
OAuth 인증 그대로 사용.

**철칙 1**: D4 — raw 텍스트를 그대로 cloud claude CLI에 전달한다 (redaction 제거).
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
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, cast

from synapse_memory.cost.events import append_cost_event, build_cost_event
from synapse_memory.cost.pricing import price_usage
from synapse_memory.llm.tokens import estimate_tokens

CLAUDE_BIN = "claude"
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SEC = 60

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?\s*```\s*$",
    re.DOTALL,
)


def _known_claude_paths() -> tuple[str, ...]:
    return (
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
    )


def _resolve_claude_path() -> str | None:
    path = shutil.which(CLAUDE_BIN)
    if path:
        return path
    for candidate in _known_claude_paths():
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


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
    def ready(self) -> bool:
        return self.claude_path is not None

    def reasons_unavailable(self) -> list[str]:
        if not self.claude_path:
            return [
                "Claude Code CLI 미설치 — 설치: https://docs.claude.com/claude-code"
            ]
        return []


def detect_claude_environment(model: str = DEFAULT_MODEL) -> ClaudeEnvironment:
    path = _resolve_claude_path()
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
    return ClaudeEnvironment(
        claude_path=path, claude_version=version, model=model
    )


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
    started = time.monotonic()
    model = _model_from_cmd(cmd)
    try:
        result = subprocess.run(
            [*cmd, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        _record_claude_cost(
            model=model,
            prompt=prompt,
            result_text="",
            status="timeout",
            elapsed_s=elapsed,
            error_kind="timeout",
        )
        raise ClaudeError(f"claude 호출 타임아웃 ({timeout}s)") from exc
    except OSError as exc:
        elapsed = time.monotonic() - started
        _record_claude_cost(
            model=model,
            prompt=prompt,
            result_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="os_error",
        )
        raise ClaudeError(f"claude 실행 실패: {exc}") from exc
    elapsed = time.monotonic() - started

    if result.returncode != 0:
        _record_claude_cost(
            model=model,
            prompt=prompt,
            result_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="nonzero_exit",
        )
        msg = (
            result.stderr.strip()
            or result.stdout.strip()[:500]
            or "(no output)"
        )
        raise ClaudeError(
            f"claude 비정상 종료 exit={result.returncode}: {msg}"
        )

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        _record_claude_cost(
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
        _record_claude_cost(
            model=_model_from_envelope(normalized, fallback=model),
            prompt=prompt,
            result_text=str(normalized.get("result") or ""),
            status="error",
            elapsed_s=elapsed,
            envelope=normalized,
            error_kind=str(normalized.get("subtype") or "envelope_error"),
        )
        msg = normalized.get("result") or normalized.get("subtype") or "unknown"
        raise ClaudeError(f"Claude 응답 에러: {msg}")

    _record_claude_cost(
        model=_model_from_envelope(normalized, fallback=model),
        prompt=prompt,
        result_text=str(normalized.get("result") or ""),
        status="success",
        elapsed_s=elapsed,
        envelope=normalized,
    )
    return normalized


def _record_claude_cost(
    *,
    model: str,
    prompt: str,
    result_text: str,
    status: str,
    elapsed_s: float,
    envelope: dict[str, Any] | None = None,
    error_kind: str | None = None,
) -> None:
    envelope = envelope or {}
    input_tokens, output_tokens = _usage_from_envelope(envelope)
    if input_tokens == 0:
        input_tokens = estimate_tokens(prompt)
    if output_tokens == 0 and result_text:
        output_tokens = estimate_tokens(result_text)
    provider_usd = _provider_usd(envelope)
    priced = price_usage(
        provider="claude",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        provider_usd=provider_usd,
    )
    try:
        append_cost_event(
            build_cost_event(
                provider="claude",
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


def _model_from_cmd(cmd: list[str]) -> str:
    if "--model" in cmd:
        idx = cmd.index("--model")
        if idx + 1 < len(cmd):
            return cmd[idx + 1]
    return DEFAULT_MODEL


def _model_from_envelope(envelope: dict[str, Any], *, fallback: str) -> str:
    raw = envelope.get("model") or envelope.get("model_id")
    return str(raw) if raw else fallback


def _usage_from_envelope(envelope: dict[str, Any]) -> tuple[int, int]:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = _first_int(
        envelope,
        usage,
        keys=("input_tokens", "prompt_tokens"),
    )
    output_tokens = _first_int(
        envelope,
        usage,
        keys=("output_tokens", "completion_tokens"),
    )
    return input_tokens, output_tokens


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


def _provider_usd(envelope: dict[str, Any]) -> float | None:
    for key in ("total_cost_usd", "cost_usd", "usd"):
        value = envelope.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


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
    system: str | None,
    model: str | None,
    json_schema: dict[str, Any] | None,
    max_budget_usd: float | None,
    timeout: int,
    env: ClaudeEnvironment | None,
) -> dict[str, Any]:
    """공통 준비(env 진단 + cmd 빌드) + CLI 호출 → normalized envelope dict.

    ``complete``(텍스트)와 ``complete_structured``(structured_output) 양쪽이
    동일 호출 경로를 공유하도록 추출.
    """
    env = env or detect_claude_environment(model or DEFAULT_MODEL)
    _ensure_ready(env)
    cmd = _build_cmd(
        env,
        system=system,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
    )
    return _run_claude(cmd, prompt=prompt, timeout=timeout)


def complete(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ClaudeEnvironment | None = None,
) -> str:
    """Claude Code CLI 단일 호출 → 응답 텍스트.

    Args:
        prompt: 사용자 프롬프트.
        system: 시스템 프롬프트.
        model: 모델 alias (sonnet/opus/haiku) 또는 full 이름.
        json_schema: 응답 JSON schema 강제 (Claude 자체 검증).
        max_budget_usd: 비용 cap (호출당).
        timeout: 초 단위.
        env: 사전 진단 결과.

    Returns:
        envelope.result 텍스트.
    """
    envelope = _complete_envelope(
        prompt,
        system=system,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
    )
    content = envelope.get("result", "")
    if not isinstance(content, str):
        raise ClaudeError(
            f"envelope.result가 string 아님: {type(content).__name__}"
        )
    return content


def complete_structured(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    max_budget_usd: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ClaudeEnvironment | None = None,
) -> Any:
    """JSON 응답 → parse. ``json_schema`` 명시 시 Claude가 직접 검증.

    Raises:
        ClaudeError: 호출 실패 또는 JSON 추출 실패.
    """
    envelope = _complete_envelope(
        prompt,
        system=system or _DEFAULT_STRUCTURED_SYSTEM,
        model=model,
        json_schema=json_schema,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
        env=env,
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


_DEFAULT_STRUCTURED_SYSTEM = (
    "You output ONLY a single valid JSON value. "
    "No prose, no markdown code fences, no explanation. "
    "Korean text inside JSON string values is OK."
)


def _strip_code_fence(text: str) -> str:
    m = _CODE_FENCE_RE.match(text.strip())
    if m:
        return m.group("body").strip()
    return text.strip()


def _extract_first_json_value(text: str) -> str | None:
    in_str = False
    escape = False
    depth = 0
    start = -1
    open_c = ""
    close_c = ""
    for i, c in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
            continue
        if depth == 0 and c in "{[":
            open_c = c
            close_c = "}" if c == "{" else "]"
            start = i
            depth = 1
        elif depth > 0:
            if c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _parse_json_with_fallback(content: str) -> Any:
    candidates: list[str] = [content]
    stripped = _strip_code_fence(content)
    if stripped != content:
        candidates.append(stripped)
    extracted = _extract_first_json_value(stripped)
    if extracted is not None and extracted not in candidates:
        candidates.append(extracted)

    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
    raise ClaudeError(
        f"Claude 응답이 JSON 아님: {content[:200]!r}"
    ) from last_err
