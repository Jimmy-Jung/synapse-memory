# src/synapse_memory/wiki/query.py
"""wiki-first ask — wiki 검색 → 합성 → 인용 → 선택적 insight write-back.

흐름::

    query → _retrieve_wiki(provider select_related) → 컨텍스트 →
    ai_api.complete(system=ASK_WIKI_SYSTEM) → [[slug]] 인용 답변 →
    (save=True) insight WikiPage write-back

원칙(D4: redaction 없음)
- 제공된 wiki 페이지**만** 근거. 각 주장에 ``[[slug]]`` 인용.
- 자료 없으면 "자료에 없음". 한국어, 짧고 정확.

테스트 격리를 위해 `_retrieve_wiki`/`ai_api.complete`를 모듈 속성으로 두어
monkeypatch 가능하게 한다. provider 부재/오류 시 `_retrieve_wiki`는
graceful `[]`를 반환한다.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from synapse_memory.llm import ai_api
from synapse_memory.wiki.page import (
    WikiPage,
    extract_wikilinks,
    save_page,
    slugify,
)

AIEnv = ai_api.AIEnvironment | ai_api.AIProviderEnv | None

ASK_WIKI_SYSTEM = """당신은 사용자의 개인 지식 wiki를 근거로 답하는 세컨드 브레인입니다.

# 원칙
- 아래 제공된 wiki 페이지**만** 근거로 답변합니다.
- 자료에 없는 정보는 **추측하지 않습니다** — "자료에 없음"이라고 솔직히 답합니다.
- 각 주장 끝에 출처를 ``[[slug]]`` 형식으로 인용합니다.
- 한국어로 자연스럽게, 사용자에게 직접 말하듯 답변합니다.
- 짧고 정확하게. 불필요한 인사·반복 금지."""

DEFAULT_TOP_K = 5
SOURCE_DOC_CHARS = 2000
NO_RESULTS_ANSWER = "자료에 없음 — 먼저 ingest/reindex 하세요."
INSIGHT_SLUG_MAX = 60


@dataclass
class WikiAnswer:
    query: str
    answer: str
    sources: list[str] = field(default_factory=list)
    saved_slug: str | None = None


def _retrieve_wiki(
    query: str,
    *,
    vault_path: Path | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[WikiPage]:
    """provider LLM(claude|codex)로 관련 wiki 페이지를 선별·로드 (020).

    로컬 임베딩/벡터스토어 제거 — PageIndex를 provider에 넘겨 관련 slug를
    고른 뒤 해당 페이지를 반환한다. 빈 vault/오류 시 ``[]`` (graceful).
    """
    from synapse_memory.wiki.llm_retrieval import select_related
    from synapse_memory.wiki.page_index import build_page_index
    from synapse_memory.wiki.retrieval import _all_pages

    all_pages = _all_pages(vault_path)
    if not all_pages:
        return []
    index = build_page_index(all_pages)
    by_slug = {p.slug: p for p in all_pages}
    slugs = select_related(query, index, max_pages=top_k)
    return [by_slug[s] for s in slugs if s in by_slug]


def _build_context(pages: list[WikiPage]) -> str:
    parts = [
        f"[[{page.slug}]] {page.title}\n{page.body[:SOURCE_DOC_CHARS]}"
        for page in pages
    ]
    return "\n\n".join(parts)


def _resolve_sources(answer: str, pages: list[WikiPage]) -> list[str]:
    """인용된 slug 우선, 비면 retrieved slug."""
    cited = extract_wikilinks(answer)
    page_slugs = [p.slug for p in pages if p.slug in answer]
    sources = list(dict.fromkeys(cited + page_slugs))
    if sources:
        return sources
    return [p.slug for p in pages]


def ask_wiki(
    query: str,
    *,
    vault_path: Path | None = None,
    top_k: int = DEFAULT_TOP_K,
    model: str | None = None,
    ai_env: AIEnv = None,
    save: bool = False,
    today: str | None = None,
) -> WikiAnswer:
    """wiki-first 질의 → 합성 답변 + 인용. save=True면 insight 페이지로 환원."""
    pages = _retrieve_wiki(query, vault_path=vault_path, top_k=top_k)
    if not pages:
        return WikiAnswer(query=query, answer=NO_RESULTS_ANSWER, sources=[])

    context = _build_context(pages)
    user_prompt = (
        f"# 질문\n{query}\n\n"
        f"# 자료\n{context}\n\n"
        f"위 wiki 페이지를 근거로 답변하세요. 추측 금지. 각 주장에 [[slug]] 인용."
    )
    answer = ai_api.complete(
        user_prompt,
        system=ASK_WIKI_SYSTEM,
        model=model,
        env=ai_env,
        timeout=120,
    )
    sources = _resolve_sources(answer, pages)

    saved_slug: str | None = None
    if save:
        saved_slug = _write_back(query, answer, sources, vault_path=vault_path, today=today)

    return WikiAnswer(query=query, answer=answer, sources=sources, saved_slug=saved_slug)


def _write_back(
    query: str,
    answer: str,
    sources: list[str],
    *,
    vault_path: Path | None,
    today: str | None,
) -> str:
    """답변을 insight WikiPage로 저장 + best-effort 재인덱싱. 반환: slug."""
    slug = slugify(query)[:INSIGHT_SLUG_MAX] or "insight"
    page = WikiPage(
        type="insight",
        slug=slug,
        title=query,
        body=answer,
        related=tuple(f"[[{s}]]" for s in sources),
        sources=("ask",),
        updated=today or date.today().isoformat(),
    )
    save_page(page, vault_path=vault_path)
    # 020: 벡터 재인덱싱 제거 — provider-only(로컬 임베딩 미사용). 페이지는 디스크에만.
    return slug
