"""Project/Company Card → 벡터 DB 인덱싱.

흐름::

    list_project_cards() / list_company_cards() →
        each card → searchable text (yaml 메타 + body 합침) →
        bge-m3 batch encode → ChromaDB upsert

ID 형식:
    "card_project:<project_id>"
    "card_company:<company_id>"

Metadata: source_kind, card_id, display_name, status, domains, stack, keywords, ...

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.cards.company import (
    CompanyCard,
    list_company_cards,
)
from synapse_memory.cards.project import (
    ProjectCard,
    list_project_cards,
)
from synapse_memory.feedback.apply import (
    DEFAULT_FEEDBACK_SCORE,
    FeedbackAggregate,
    card_feedback_scores,
)
from synapse_memory.feedback.events import load_feedback_events
from synapse_memory.rag.bm25 import (
    BM25Document,
    tokenize_for_bm25,
    write_bm25_documents,
)
from synapse_memory.rag.chunker import (
    RawChunk,
    discover_raw_sources,
    raw_chunks_from_file,
)
from synapse_memory.rag.embeddings import embed_texts
from synapse_memory.rag.vector_store import (
    VectorRecord,
    VectorStore,
    open_vector_store,
)
from synapse_memory.redaction import redact_full

PREFIX_PROJECT = "card_project:"
PREFIX_COMPANY = "card_company:"


@dataclass
class IndexStats:
    project_cards: int = 0
    company_cards: int = 0
    raw_obsidian_chunks: int = 0
    raw_claude_code_chunks: int = 0
    bm25_documents: int = 0
    bytes_indexed: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_cards(self) -> int:
        return self.project_cards + self.company_cards

    @property
    def total_raw_chunks(self) -> int:
        return self.raw_obsidian_chunks + self.raw_claude_code_chunks


# ---------------------------------------------------------------------------
# Card → 검색 텍스트 변환
# ---------------------------------------------------------------------------


def project_card_to_text(card: ProjectCard) -> str:
    """ProjectCard → 검색용 단일 텍스트.

    yaml 필드 + body 통합. bge-m3 8K 토큰 안에 들어가도록 trim.
    """
    lines: list[str] = [f"# {card.display_name}"]
    if card.role:
        lines.append(f"역할: {card.role}")
    period = card.period_start or ""
    if card.period_end:
        period = f"{period} ~ {card.period_end}".strip(" ~")
    if period:
        lines.append(f"기간: {period}")
    if card.status:
        lines.append(f"상태: {card.status}")
    if card.domains:
        lines.append(f"도메인: {', '.join(card.domains)}")
    if card.stack:
        lines.append(f"기술 스택: {', '.join(card.stack)}")
    if card.keywords:
        lines.append(f"키워드: {', '.join(card.keywords)}")
    if card.metrics:
        lines.append("지표:")
        for m in card.metrics:
            if m.value:
                lines.append(f"  - {m.name}: {m.value}")
            elif m.before or m.after:
                lines.append(f"  - {m.name}: {m.before or ''} → {m.after or ''}")
    if card.body:
        lines.append("")
        lines.append(card.body.strip())
    return "\n".join(lines)


def company_card_to_text(card: CompanyCard) -> str:
    """CompanyCard → 검색용 단일 텍스트."""
    lines: list[str] = [f"# {card.display_name}"]
    if card.country:
        lines.append(f"국가: {card.country}")
    if card.size:
        lines.append(f"규모: {card.size}")
    if card.status:
        lines.append(f"상태: {card.status}")
    if card.website:
        lines.append(f"웹사이트: {card.website}")
    if card.positions:
        lines.append("포지션:")
        for p in card.positions:
            extras: list[str] = []
            if p.seniority:
                extras.append(p.seniority)
            if p.keywords:
                extras.append(", ".join(p.keywords))
            extras_str = f" ({'; '.join(extras)})" if extras else ""
            lines.append(f"  - {p.title}{extras_str}")
    if card.body:
        lines.append("")
        lines.append(card.body.strip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metadata 빌더
# ---------------------------------------------------------------------------


def _project_meta(card: ProjectCard) -> dict[str, object]:
    return {
        "source_kind": "card_project",
        "card_id": card.project_id,
        "display_name": card.display_name,
        "status": card.status,
        "role": card.role or "",
        "period_start": card.period_start or "",
        "period_end": card.period_end or "",
        "domains": list(card.domains),
        "stack": list(card.stack),
        "keywords": list(card.keywords),
        "created": card.created or "",
        "last_reviewed": card.last_reviewed or "",
        "confidence": card.confidence,
    }


def _company_meta(card: CompanyCard) -> dict[str, object]:
    return {
        "source_kind": "card_company",
        "card_id": card.company_id,
        "display_name": card.display_name,
        "status": card.status,
        "country": card.country or "",
        "size": card.size or "",
        "website": card.website or "",
        "created": card.created or "",
        "last_reviewed": card.last_reviewed or "",
        "confidence": card.confidence,
    }


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------


def index_cards(
    *,
    store: VectorStore | None = None,
    vault_path: Path | None = None,
    rebuild: bool = False,
    include_raw: bool = False,
    bm25_path: Path | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    batch_size: int = 16,
) -> IndexStats:
    """vault의 모든 Project/Company Card를 임베딩 → 벡터 DB upsert.

    Args:
        store: VectorStore (기본: ``open_vector_store()``).
        vault_path: vault 위치 (기본: 자동 감지).
        rebuild: True면 collection 비우고 처음부터.
        include_raw: True면 vault/L0 raw chunks 도 인덱싱.
        bm25_path: BM25 sidecar 경로 override (테스트용).
        on_progress: ``(stage, current, total)`` 콜백 (stage="project"|"company").
        batch_size: 임베딩 배치.

    Returns:
        IndexStats — 인덱싱된 Card 수와 byte.
    """
    store = store or open_vector_store()

    if rebuild:
        store.clear()

    stats = IndexStats()

    projects = list_project_cards(vault_path=vault_path)
    companies = list_company_cards(vault_path=vault_path)
    feedback_scores = card_feedback_scores(load_feedback_events(recover=True))
    bm25_documents: list[BM25Document] = []

    # ---- Project Card ----
    if projects:
        project_records: list[VectorRecord] = []
        texts = [project_card_to_text(c) for c in projects]
        vectors = embed_texts(texts, batch_size=batch_size)

        for i, (card, text, vec) in enumerate(
            zip(projects, texts, vectors, strict=False)
        ):
            if on_progress:
                on_progress("project", i + 1, len(projects))
            project_records.append(
                VectorRecord(
                    id=f"{PREFIX_PROJECT}{card.project_id}",
                    document=text,
                    embedding=vec,
                    metadata={
                        **_project_meta(card),
                        "feedback_score": _feedback_score(
                            feedback_scores, card.project_id
                        ),
                    },
                )
            )
            stats.bytes_indexed += len(text.encode())

        try:
            store.upsert(project_records)
            stats.project_cards = len(project_records)
            bm25_documents.extend(_bm25_documents_from_records(project_records))
        except Exception as exc:
            stats.failed.append(("project_upsert", str(exc)))

    # ---- Company Card ----
    if companies:
        company_records: list[VectorRecord] = []
        texts = [company_card_to_text(c) for c in companies]
        vectors = embed_texts(texts, batch_size=batch_size)

        for i, (company, text, vec) in enumerate(
            zip(companies, texts, vectors, strict=False)
        ):
            if on_progress:
                on_progress("company", i + 1, len(companies))
            company_records.append(
                VectorRecord(
                    id=f"{PREFIX_COMPANY}{company.company_id}",
                    document=text,
                    embedding=vec,
                    metadata={
                        **_company_meta(company),
                        "feedback_score": _feedback_score(
                            feedback_scores, company.company_id
                        ),
                    },
                )
            )
            stats.bytes_indexed += len(text.encode())

        try:
            store.upsert(company_records)
            stats.company_cards = len(company_records)
            bm25_documents.extend(_bm25_documents_from_records(company_records))
        except Exception as exc:
            stats.failed.append(("company_upsert", str(exc)))

    if include_raw:
        raw_records = _build_raw_records(
            vault_path=vault_path,
            on_progress=on_progress,
            batch_size=batch_size,
            stats=stats,
        )
        if raw_records:
            try:
                store.upsert(raw_records)
                bm25_documents.extend(_bm25_documents_from_records(raw_records))
            except Exception as exc:
                stats.failed.append(("raw_upsert", str(exc)))

        try:
            write_bm25_documents(bm25_documents, path=bm25_path)
            stats.bm25_documents = len(bm25_documents)
        except Exception as exc:
            stats.failed.append(("bm25_write", str(exc)))

    return stats


def _build_raw_records(
    *,
    vault_path: Path | None,
    on_progress: Callable[[str, int, int], None] | None,
    batch_size: int,
    stats: IndexStats,
) -> list[VectorRecord]:
    sources = discover_raw_sources(vault_path=vault_path)
    chunks: list[RawChunk] = []
    for index, source in enumerate(sources, start=1):
        if on_progress:
            on_progress(source.source_kind, index, len(sources))
        try:
            chunks.extend(
                raw_chunks_from_file(
                    source.path,
                    source_kind=source.source_kind,
                    root_path=source.root_path,
                    redact=lambda text: redact_full(text).redacted,
                )
            )
        except Exception as exc:
            stats.failed.append((f"{source.source_kind}:{source.path.name}", str(exc)))

    if not chunks:
        return []

    texts = [chunk.text for chunk in chunks]
    vectors = embed_texts(texts, batch_size=batch_size)
    records: list[VectorRecord] = []
    for chunk, vector in zip(chunks, vectors, strict=False):
        records.append(
            VectorRecord(
                id=chunk.id,
                document=chunk.text,
                embedding=vector,
                metadata={
                    "source_kind": chunk.source_kind,
                    "path": chunk.path,
                    "chunk_index": chunk.chunk_index,
                    "display_name": chunk.display_name,
                    "created": chunk.created,
                },
            )
        )
        stats.bytes_indexed += len(chunk.text.encode())
        if chunk.source_kind == "raw_obsidian":
            stats.raw_obsidian_chunks += 1
        elif chunk.source_kind == "raw_claude_code":
            stats.raw_claude_code_chunks += 1
    return records


def _bm25_documents_from_records(records: list[VectorRecord]) -> list[BM25Document]:
    return [
        BM25Document(
            record_id=record.id,
            text=record.document,
            tokens=tokenize_for_bm25(record.document),
            metadata=dict(record.metadata),
        )
        for record in records
    ]


def _feedback_score(
    feedback_scores: dict[str, FeedbackAggregate],
    card_id: str,
) -> float:
    aggregate = feedback_scores.get(card_id)
    return aggregate.score if aggregate is not None else DEFAULT_FEEDBACK_SCORE
