# src/synapse_memory/wiki/index.py
"""wiki 페이지 → rag 벡터 스토어 인덱싱 (store/embed 주입 가능).

rag(`open_vector_store`/`embed_texts`/`VectorRecord`)를 재사용하되 대상을
카드가 아닌 wiki 페이지로 둔다. 레코드 id는 ``wiki:<type>:<slug>``,
metadata는 ``{"source_kind": "wiki", "type", "slug", "title"}`` — 검색 시
``where={"source_kind": "wiki"}``로 스코프할 수 있다.

테스트 격리를 위해 store/embed_fn을 주입 가능하게 설계한다. 미지정이면
rag 기본값(`open_vector_store`/`embed_texts`)을 지연 import해 사용한다.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from synapse_memory.rag import VectorRecord
from synapse_memory.wiki.page import VALID_TYPES, WikiPage, list_pages

WIKI_SOURCE_KIND = "wiki"

EmbedFn = Callable[[list[str]], Sequence[Sequence[float]]]


def wiki_page_to_text(page: WikiPage) -> str:
    """페이지 → 임베딩/검색 대상 텍스트 (title + body)."""
    return f"{page.title}\n\n{page.body}"


def wiki_page_to_record(page: WikiPage, *, embedding: Sequence[float]) -> VectorRecord:
    """페이지 + 임베딩 → VectorRecord."""
    return VectorRecord(
        id=f"wiki:{page.type}:{page.slug}",
        document=wiki_page_to_text(page),
        embedding=list(embedding),
        metadata={
            "source_kind": WIKI_SOURCE_KIND,
            "type": page.type,
            "slug": page.slug,
            "title": page.title,
        },
    )


def _resolve_embed(embed_fn: EmbedFn | None) -> EmbedFn:
    if embed_fn is not None:
        return embed_fn
    from synapse_memory.rag import embed_texts

    return embed_texts


def _resolve_store(store: Any | None) -> Any:
    if store is not None:
        return store
    from synapse_memory.rag import open_vector_store

    return open_vector_store()


def index_wiki_pages(
    *,
    vault_path: Path | None = None,
    store: Any | None = None,
    embed_fn: EmbedFn | None = None,
) -> int:
    """모든 wiki 페이지를 임베딩 → 벡터 스토어에 upsert. 반환: upsert 수."""
    pages: list[WikiPage] = []
    for page_type in VALID_TYPES:
        pages.extend(list_pages(page_type, vault_path=vault_path))
    if not pages:
        return 0

    embed = _resolve_embed(embed_fn)
    embeddings = embed([wiki_page_to_text(p) for p in pages])
    records = [
        wiki_page_to_record(page, embedding=embedding)
        for page, embedding in zip(pages, embeddings, strict=True)
    ]
    return _resolve_store(store).upsert(records)


def index_one_page(
    page: WikiPage,
    *,
    store: Any | None = None,
    embed_fn: EmbedFn | None = None,
) -> None:
    """단일 페이지를 임베딩 → 벡터 스토어에 upsert."""
    embed = _resolve_embed(embed_fn)
    embedding = embed([wiki_page_to_text(page)])[0]
    record = wiki_page_to_record(page, embedding=embedding)
    _resolve_store(store).upsert([record])
