# src/synapse_memory/wiki/backfill.py
"""초기 백필 — 빈 vault에서 전체 raw 이력을 배치 단위로 재구축(재개 가능).

P1 ``ingest_source``를 per-doc 체크포인트(``checkpoint_each=True``)로 배치 호출해
소진될 때까지 반복한다. 과거 이력은 전부 settled이므로 유휴 필터(min_age)는 끈다.
중단되면 watermark가 doc마다 전진해 있어 재실행 시 남은 것부터 이어 처리한다.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.wiki.ingest import ingest_source


@dataclass
class BackfillResult:
    source: str
    batches: int = 0
    docs_processed: int = 0
    docs_skipped: int = 0
    pages_written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_backfill(
    *,
    source: str = "claude-code",
    vault_path: Path | None = None,
    ai_env: object | None = None,
    batch_size: int = 20,
    max_batches: int | None = None,
    today: str | None = None,
    semantic_retrieval: bool = True,
) -> BackfillResult:
    """배치 단위로 ``ingest_source``를 소진될 때까지 반복 호출.

    각 배치는 ``checkpoint_each=True``(doc마다 watermark 저장)와 ``min_age_seconds=None``
    (유휴 필터 끔)로 실행된다. ``docs_processed == 0``(소진) 또는 ``max_batches`` 도달 시 종료.
    """
    result = BackfillResult(source=source)
    while True:
        batch = ingest_source(
            source,
            vault_path=vault_path,
            ai_env=ai_env,
            limit=batch_size,
            checkpoint_each=True,
            min_age_seconds=None,
            today=today,
            semantic_retrieval=semantic_retrieval,
        )
        result.batches += 1
        result.docs_processed += batch.docs_processed
        result.docs_skipped += batch.docs_skipped
        result.pages_written.extend(batch.pages_written)
        result.errors.extend(batch.errors)
        # 진전 없음(배치 전부 실패) → 무한루프 방지
        if (
            batch.docs_processed > 0
            and batch.docs_skipped == 0
            and len(batch.errors) >= batch.docs_processed
        ):
            break
        if batch.docs_processed == 0:
            break
        if max_batches is not None and result.batches >= max_batches:
            break
    return result
