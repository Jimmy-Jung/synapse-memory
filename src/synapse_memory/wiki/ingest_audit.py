# src/synapse_memory/wiki/ingest_audit.py
"""ingest pending queue 비용 감사 — LLM 호출 없이 raw 크기만 집계."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from synapse_memory.wiki.ingest import classify_ingest_text
from synapse_memory.wiki.rawdoc import iter_new_raw
from synapse_memory.wiki.watermark import load_watermark


@dataclass(frozen=True)
class IngestAuditResult:
    source: str
    docs_pending: int = 0
    docs_small: int = 0
    docs_sampled: int = 0
    docs_oversize: int = 0
    estimated_llm_calls: int = 0
    max_chars: int = 0


def audit_ingest_queue(
    source: str,
    *,
    raw_root: Path | None = None,
    watermark_path: Path | None = None,
    limit: int | None = None,
    min_age_seconds: float | None = None,
    semantic_retrieval: bool = True,
) -> IngestAuditResult:
    """watermark 이후 pending raw 문서를 읽고 비용 라우팅만 계산한다."""
    since = load_watermark(source, path=watermark_path)
    docs_all = iter_new_raw(
        source,
        since=since,
        root=raw_root,
        min_age_seconds=min_age_seconds,
    )
    docs = islice(docs_all, limit) if limit is not None else docs_all

    docs_pending = 0
    docs_small = 0
    docs_sampled = 0
    docs_oversize = 0
    estimated_llm_calls = 0
    max_chars = 0

    for doc in docs:
        route = classify_ingest_text(
            doc.text,
            semantic_retrieval=semantic_retrieval,
        )
        docs_pending += 1
        max_chars = max(max_chars, route.text_chars)
        estimated_llm_calls += route.estimated_llm_calls
        if route.kind == "small":
            docs_small += 1
        elif route.kind == "sampled":
            docs_sampled += 1
        else:
            docs_oversize += 1

    return IngestAuditResult(
        source=source,
        docs_pending=docs_pending,
        docs_small=docs_small,
        docs_sampled=docs_sampled,
        docs_oversize=docs_oversize,
        estimated_llm_calls=estimated_llm_calls,
        max_chars=max_chars,
    )
