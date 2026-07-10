"""LLM-as-retriever shared index selector.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from typing import Any, Protocol

from synapse_memory.llm import ai_api
from synapse_memory.retrieval.provider import _provider

AIEnv = ai_api.AIEnvironment | ai_api.AIProviderEnv | None

# 프롬프트에 넣는 doc 발췌 상한 — 거대 세션 전문 통째 투입 금지.
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
    "당신은 지식베이스 사서입니다. 주어진 인덱스에서 새 문서와 "
    "의미적으로 관련된 항목만 고릅니다. 인덱스에 없는 식별자는 절대 만들지 마세요. "
    "관련 없으면 빈 목록을 반환합니다."
)

_SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "related": {
            "type": "array",
            "items": {"type": "string"},
            "description": "관련된 식별자 목록 (인덱스에 존재하는 것만)",
        }
    },
    "required": ["related"],
    "additionalProperties": False,
}


def _relevance_model(env: AIEnv = None) -> str | None:
    """provider별 relevance 모델. 해석 실패 시 None(provider default)."""
    return ai_api.resolve_model_for_task(
        "relevance", provider=getattr(env, "provider", None)
    )


def select_related(
    doc_text: str,
    index: SelectableIndex,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    env: AIEnv = None,
    model: str | None = None,
    timeout: int = 60,
) -> list[str]:
    """doc과 관련된 index 식별자 목록. provider 실패/빈 인덱스 → ``[]``."""
    if not index.entries or not doc_text.strip():
        return []

    excerpt = doc_text[:MAX_DOC_CHARS]
    prompt = (
        f"# 인덱스\n{index.render()}\n\n"
        f"# 새 문서 (발췌)\n{excerpt}\n\n"
        f"위 인덱스에서 이 문서와 관련된 식별자를 최대 {max_pages}개 고르세요. "
        "관련 없으면 빈 목록."
    )
    try:
        payload = ai_api.complete_structured(
            prompt,
            system=_SELECT_SYSTEM,
            model=model or _relevance_model(env),
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
