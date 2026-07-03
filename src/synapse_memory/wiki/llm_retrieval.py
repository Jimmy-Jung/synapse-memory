# src/synapse_memory/wiki/llm_retrieval.py
"""LLM-as-retriever — 로컬 임베딩 대체 (020).

`config.ai_provider`(claude|codex)가 선택한 provider가 PageIndex를 직접 읽고
관련 페이지 slug를 고르거나, 질의에 대해 선별+답변을 합성한다. 로컬 ML 없음 —
`ai_api.complete_structured`/`complete` facade를 통해 provider로 일원화.

저자: Synapse Memory Maintainers
작성일: 2026-06-16
"""
from __future__ import annotations

from typing import Any, Protocol

from synapse_memory.llm import ai_api

AIEnv = ai_api.AIEnvironment | ai_api.AIProviderEnv | None

# 프롬프트에 넣는 doc 발췌 상한 — 거대 세션 전문 통째 투입 금지(메모리/토큰 폭발 방지).
MAX_DOC_CHARS = 6000
DEFAULT_MAX_PAGES = 12


class SelectableIndex(Protocol):
    """``select_related``가 요구하는 최소 index 계약."""

    @property
    def entries(self) -> tuple[Any, ...]: ...

    @property
    def slugs(self) -> frozenset[str]: ...

    def render(self) -> str: ...

_SELECT_SYSTEM = (
    "당신은 지식베이스 사서입니다. 주어진 위키 페이지 인덱스에서 새 문서와 "
    "의미적으로 관련된 페이지만 고릅니다. 인덱스에 없는 slug는 절대 만들지 마세요. "
    "관련 없으면 빈 목록을 반환합니다."
)

_SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "related": {
            "type": "array",
            "items": {"type": "string"},
            "description": "관련된 페이지 slug 목록 (인덱스에 존재하는 것만)",
        }
    },
    "required": ["related"],
    "additionalProperties": False,
}

def _provider() -> ai_api.AIProvider | None:
    """config.ai_provider — auto면 None(ai_api가 런타임 감지)."""
    try:
        from synapse_memory.config import get_config

        provider = get_config().ai_provider
        if provider == "claude":
            return "claude"
        if provider == "codex":
            return "codex"
        return None
    except Exception:
        return None


def _relevance_model() -> str | None:
    """models.<provider>.relevance — 싼 티어. 해석 실패 시 None(provider default)."""
    try:
        from synapse_memory.config import get_config

        cfg = get_config()
        if cfg.ai_provider == "auto":
            return None
        provider_models = getattr(cfg.models, cfg.ai_provider, None)
        return getattr(provider_models, "relevance", None) if provider_models else None
    except Exception:
        return None


def select_related(
    doc_text: str,
    index: SelectableIndex,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    env: AIEnv = None,
    model: str | None = None,
    timeout: int = 60,
) -> list[str]:
    """doc과 관련된 페이지 slug 목록. provider 호출. 실패/빈 인덱스 → [] (graceful).

    ingest 핫패스에서 호출되므로 어떤 예외도 삼키고 빈 목록을 반환해 통합을 막지
    않는다(이름매칭/1-hop 폴백이 retrieval에 남아있음).
    """
    if not index.entries or not doc_text.strip():
        return []

    excerpt = doc_text[:MAX_DOC_CHARS]
    prompt = (
        f"# 위키 페이지 인덱스\n{index.render()}\n\n"
        f"# 새 문서 (발췌)\n{excerpt}\n\n"
        f"위 인덱스에서 이 문서와 관련된 페이지 slug를 최대 {max_pages}개 고르세요. "
        "관련 없으면 빈 목록."
    )
    try:
        payload = ai_api.complete_structured(
            prompt,
            system=_SELECT_SYSTEM,
            model=model or _relevance_model(),
            json_schema=_SELECT_SCHEMA,
            timeout=timeout,
            env=env,
            provider=_provider() if env is None else None,
        )
    except Exception:
        return []

    raw = payload.get("related", []) if isinstance(payload, dict) else []
    valid = index.slugs
    out: list[str] = []
    seen: set[str] = set()
    for slug in raw:
        s = str(slug).strip()
        if s in valid and s not in seen:
            out.append(s)
            seen.add(s)
        if len(out) >= max_pages:
            break
    return out
