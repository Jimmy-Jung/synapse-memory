"""LLM 응답 → JSON 파싱 공통 헬퍼.

claude / codex 어댑터가 모두 같은 방식 — 코드펜스 제거 → 첫 JSON 값 추출 →
``json.loads`` 다단 fallback — 으로 응답을 파싱한다. 본 모듈에 통합.

저자: Synapse Memory Maintainers
작성일: 2026-06-22
"""

from __future__ import annotations

import json
import re
from typing import Any

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?\s*```\s*$",
    re.DOTALL,
)


def strip_code_fence(text: str) -> str:
    m = _CODE_FENCE_RE.match(text.strip())
    if m:
        return m.group("body").strip()
    return text.strip()


def extract_first_json_value(text: str) -> str | None:
    """``text`` 안 첫 균형 잡힌 JSON object/array 의 raw substring."""
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


def parse_json_with_fallback(
    content: str,
    *,
    error_cls: type[Exception],
    provider: str,
) -> Any:
    """원문 → 코드펜스 제거 → 첫 JSON 추출 순으로 ``json.loads`` 시도.

    Args:
        content: LLM 원문 응답.
        error_cls: 모두 실패 시 raise 할 예외 클래스 (provider별).
        provider: 에러 메시지용 provider 이름 (예: "Claude", "Codex").
    """
    candidates: list[str] = [content]
    stripped = strip_code_fence(content)
    if stripped != content:
        candidates.append(stripped)
    extracted = extract_first_json_value(stripped)
    if extracted is not None and extracted not in candidates:
        candidates.append(extracted)

    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
    raise error_cls(f"{provider} 응답이 JSON 아님: {content[:200]!r}") from last_err
