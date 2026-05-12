"""Claude Code CLI wrapper — Anthropic API SDK 대신 ``claude`` 명령 subprocess.

apfel과 같은 패턴 (CLI subprocess). API key 별도 발급 불필요 — 사용자 Claude Code
OAuth 인증 그대로 사용.

**철칙 1**: 입력 텍스트는 반드시 ``redact_full`` 통과된 redacted 형태.
**철칙 2**: 비용 절감 — ``--system-prompt``로 default system prompt 대체.
   default 사용 시 CLAUDE.md/memory/plugins가 자동 합쳐져 35K+ cache 만들어짐 ($0.24/call).
   ``--system-prompt`` 명시하면 dynamic sections 자동 제외 → ~$0.001/call.

NOTE: ``--bare`` 모드는 OAuth/keychain 인증을 무시하고 ANTHROPIC_API_KEY만 받음.
사용자가 Pro/Max 구독으로 OAuth 인증한 경우 사용 불가 → bare 안 씀.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

CLAUDE_BIN = "claude"
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SEC = 60

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?\s*```\s*$",
    re.DOTALL,
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
    def ready(self) -> bool:
        return self.claude_path is not None

    def reasons_unavailable(self) -> list[str]:
        if not self.claude_path:
            return [
                "Claude Code CLI 미설치 — 설치: https://docs.claude.com/claude-code"
            ]
        return []


def detect_claude_environment(model: str = DEFAULT_MODEL) -> ClaudeEnvironment:
    path = shutil.which(CLAUDE_BIN)
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
    json_schema: dict | None,
    max_budget_usd: float | None,
) -> list[str]:
    """공통 옵션 — non-interactive + json envelope + system-prompt 강제.

    ``--system-prompt`` 항상 설정 — 사용자 CLAUDE.md/memory/plugins/dynamic sections이
    cache로 들어가는 것 방지 (cache_creation 35K → 0).
    """
    assert env.claude_path is not None
    cmd: list[str] = [
        env.claude_path,
        "--print",
        "--output-format", "json",
        "--no-session-persistence",
        "--permission-mode", "bypassPermissions",  # tool 안 씀, 권한 묻기 skip
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
) -> dict:
    """subprocess + envelope JSON 파싱. envelope dict 반환."""
    try:
        result = subprocess.run(
            [*cmd, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeError(f"claude 호출 타임아웃 ({timeout}s)") from exc
    except OSError as exc:
        raise ClaudeError(f"claude 실행 실패: {exc}") from exc

    if result.returncode != 0:
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
        raise ClaudeError(
            f"envelope JSON 파싱 실패: {result.stdout[:200]!r}"
        ) from exc

    envelope = _normalize_envelope(envelope)

    if envelope.get("is_error"):
        msg = envelope.get("result") or envelope.get("subtype") or "unknown"
        raise ClaudeError(f"Claude 응답 에러: {msg}")

    return envelope


def _normalize_envelope(envelope: Any) -> dict[str, Any]:
    """Claude Code JSON output variants → final result envelope.

    Claude Code 2.1+ can return a JSON event array for ``--output-format json``.
    The final event with ``type == "result"`` contains the same result fields
    that older single-dict output exposed directly.
    """
    if isinstance(envelope, dict):
        return envelope

    if isinstance(envelope, list):
        for event in reversed(envelope):
            if isinstance(event, dict) and event.get("type") == "result":
                return event
        raise ClaudeError("Claude event stream에 result event 없음")

    raise ClaudeError(f"envelope이 dict/list 아님: {type(envelope).__name__}")


def complete(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    json_schema: dict | None = None,
    max_budget_usd: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ClaudeEnvironment | None = None,
) -> str:
    """Claude Code CLI 단일 호출 → 응답 텍스트.

    Args:
        prompt: 사용자 프롬프트 (redacted여야).
        system: 시스템 프롬프트.
        model: 모델 alias (sonnet/opus/haiku) 또는 full 이름.
        json_schema: 응답 JSON schema 강제 (Claude 자체 검증).
        max_budget_usd: 비용 cap (호출당).
        timeout: 초 단위.
        env: 사전 진단 결과.

    Returns:
        envelope.result 텍스트.
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
    envelope = _run_claude(cmd, prompt=prompt, timeout=timeout)

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
    json_schema: dict | None = None,
    max_budget_usd: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ClaudeEnvironment | None = None,
) -> Any:
    """JSON 응답 → parse. ``json_schema`` 명시 시 Claude가 직접 검증.

    Raises:
        ClaudeError: 호출 실패 또는 JSON 추출 실패.
    """
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
