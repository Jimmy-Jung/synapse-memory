# src/synapse_memory/wiki/ingest.py
"""ingest 오케스트레이터 — raw → 관련페이지 → 통합 → 적용 + 로그 + watermark.

엔진은 ai_api.complete_structured(json_schema=INTEGRATION_SCHEMA). raw 입력 유지(D4).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import islice
from pathlib import Path

import synapse_memory.wiki.ingest_routing as ingest_routing
from synapse_memory.llm import ai_api
from synapse_memory.retrieval.pages import _all_pages
from synapse_memory.retrieval.provider import _provider
from synapse_memory.wiki.apply import apply_ops
from synapse_memory.wiki.integration import (
    INTEGRATION_SCHEMA,
    INTEGRATION_SYSTEM,
    PageOp,
    build_integration_prompt,
    parse_ops,
)
from synapse_memory.wiki.log import append_log, summarize_provider_error
from synapse_memory.wiki.offsets import load_offsets, save_offsets
from synapse_memory.wiki.rawdoc import RawDoc, iter_new_raw, source_date_from_ref
from synapse_memory.wiki.retrieval import find_related_pages
from synapse_memory.wiki.watermark import load_watermark, save_watermark

INTEGRATION_TIMEOUT_SECONDS = 300

AIEnv = ai_api.AIEnvironment | ai_api.AIProviderEnv | None


@dataclass
class IngestResult:
    source: str
    docs_processed: int = 0
    docs_skipped: int = 0
    pages_written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _stamp_sources(ops: list[PageOp], ref: str) -> list[PageOp]:
    out: list[PageOp] = []
    for op in ops:
        if ref not in op.page.sources:
            page = replace(op.page, sources=(*op.page.sources, ref))
        else:
            page = op.page
        out.append(replace(op, page=page))
    return out


def _log_op_warnings(source: str, ops: list[PageOp]) -> None:
    for op in ops:
        for warning in op.warnings:
            append_log(
                f"ingest {source}: warning {op.page.type}/{op.page.slug}: {warning}"
            )


def _advance_watermark(current: str | None, candidate: str) -> str:
    if current is None or candidate > current:
        return candidate
    return current


def ingest_source(
    source: str,
    *,
    vault_path: Path | None = None,
    raw_root: Path | None = None,
    watermark_path: Path | None = None,
    ai_env: AIEnv = None,
    model: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    today: str | None = None,
    min_age_seconds: float | None = None,
    checkpoint_each: bool = False,
    # 토큰 절감(레버 4): small doc의 provider 관련-페이지 선별 호출을 끄면 doc당 LLM이
    # 2→1회. 선별은 lexical 휴리스틱(semantic_fn=None)으로 대체된다.
    semantic_retrieval: bool = False,
) -> IngestResult:
    """source의 새 RawDoc을 ingest. dry_run이면 적용/watermark/로그 생략.

    ``min_age_seconds``는 settled 필터로 ``iter_new_raw``에 그대로 전달된다.

    ``checkpoint_each``가 True면 doc 처리가 성공할 때마다 watermark를 저장해
    중단 후 재실행 시 남은 doc부터 이어 처리한다(재개 가능). 예외가 난 작은 doc은
    watermark를 전진시키지 않으므로 재실행 시 재시도된다. 대형 doc은 청킹 후에도
    실패하면 skipped로 격리하고 watermark를 전진시켜 backfill jam을 막는다.
    """
    since = load_watermark(source, path=watermark_path)
    offsets = load_offsets(path=watermark_path)
    docs_all = iter_new_raw(
        source, since=since, root=raw_root, min_age_seconds=min_age_seconds,
        offsets=offsets,
    )
    # 020: limit는 islice로 — 사이클당 doc 상한(메모리 천장). limit 없으면 전체.
    docs = islice(docs_all, limit) if limit is not None else docs_all

    result = IngestResult(source=source)
    # 020: 관련 페이지 선별용 전체 페이지를 사이클 1회 로드 — doc마다 재읽기 제거.
    all_pages = _all_pages(vault_path)
    max_mtime = since
    consumed: dict[str, int] = {}  # 레버 2: 소비 확정한 ref → byte offset

    def _checkpoint(doc: RawDoc) -> None:
        """doc 소비 확정 — watermark 전진 + offset 기록. checkpoint면 즉시 저장."""
        nonlocal max_mtime
        max_mtime = _advance_watermark(max_mtime, doc.mtime_iso)
        consumed[doc.ref] = doc.byte_size
        if checkpoint_each and not dry_run and max_mtime:
            save_watermark(source, max_mtime, path=watermark_path)
            save_offsets({doc.ref: doc.byte_size}, path=watermark_path)

    for doc in docs:
        result.docs_processed += 1
        # 노트의 권위 있는 날짜는 처리일(today)이 아니라 원본이 기록된 날이다.
        # codex ref 경로(sessions/YYYY/MM/DD/)에서 뽑고, 없으면 today로 폴백.
        # 제목/slug(LLM)와 updated(apply_ops) 양쪽에 같은 날짜를 흘려 보낸다.
        doc_date = source_date_from_ref(doc.ref) or today
        is_large_doc = len(doc.text) > ingest_routing.LARGE_DOC_CHAR_THRESHOLD
        chunks = ingest_routing.integration_chunks(doc.ref, doc.text)
        if not chunks:
            result.docs_skipped += 1
            if not dry_run:
                append_log(
                    f"ingest {source}: skipped oversize doc from {doc.ref} "
                    f"(chars={len(doc.text)}, limit={ingest_routing.SAMPLED_DOC_CHAR_LIMIT})",
                )
                _checkpoint(doc)
            continue
        try:
            for chunk in chunks:
                if chunk.sampled or not semantic_retrieval:
                    related = find_related_pages(
                        chunk.text,
                        vault_path=vault_path,
                        pages=all_pages,
                        semantic_fn=None,
                    )
                else:
                    related = find_related_pages(
                        chunk.text, vault_path=vault_path, pages=all_pages
                    )
                prompt = build_integration_prompt(
                    chunk.text, related, source_date=doc_date
                )
                payload = ai_api.complete_structured(
                    prompt, system=INTEGRATION_SYSTEM, model=model,
                    json_schema=INTEGRATION_SCHEMA, env=ai_env,
                    provider=_provider() if ai_env is None else None,
                    timeout=INTEGRATION_TIMEOUT_SECONDS,
                )
                ops = _stamp_sources(parse_ops(payload), chunk.ref)
                if dry_run:
                    # dry-run은 디스크에 아무것도 쓰지 않으며 pages_written도 비워 둔다
                    # (계획서 테스트 계약: result.pages_written == []).
                    continue
                _log_op_warnings(source, ops)
                written = apply_ops(ops, vault_path=vault_path, today=doc_date)
                result.pages_written.extend(written)
                # 020: 벡터 인덱싱 제거 — provider-only 검색(LLM-as-retriever).
                # 로컬 임베딩 로드를 핫패스에서 영구 차단. 페이지는 디스크에만 기록.
                if written:
                    append_log(
                        f"ingest {source}: {len(written)} pages "
                        f"({', '.join(written)}) from {chunk.ref}",
                    )
        except Exception as exc:
            error_summary = summarize_provider_error(exc)
            if is_large_doc:
                result.docs_skipped += 1
                if not dry_run:
                    append_log(
                        f"ingest {source}: skipped large doc from {doc.ref} "
                        f"after {error_summary}",
                    )
                _checkpoint(doc)
                continue
            # 실패한 작은 doc은 watermark를 전진시키지 않는다 → 재실행 시 재시도.
            result.errors.append(f"{doc.ref}: {error_summary}")
            continue
        # 성공 경로에서만 watermark 후보를 전진시킨다.
        _checkpoint(doc)

    if not dry_run and max_mtime and max_mtime != since:
        save_watermark(source, max_mtime, path=watermark_path)
    if not dry_run:
        save_offsets(consumed, path=watermark_path)
    return result
