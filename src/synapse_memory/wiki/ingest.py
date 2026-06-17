# src/synapse_memory/wiki/ingest.py
"""ingest 오케스트레이터 — raw → 관련페이지 → 통합 → 적용 + 로그 + watermark.

엔진은 ai_api.complete_structured(json_schema=INTEGRATION_SCHEMA). redaction 없음(D4).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import islice
from pathlib import Path

from synapse_memory.llm import ai_api
from synapse_memory.wiki.apply import apply_ops
from synapse_memory.wiki.integration import (
    INTEGRATION_SCHEMA,
    INTEGRATION_SYSTEM,
    PageOp,
    build_integration_prompt,
    parse_ops,
)
from synapse_memory.wiki.log import append_log
from synapse_memory.wiki.rawdoc import iter_new_raw
from synapse_memory.wiki.retrieval import _all_pages, find_related_pages
from synapse_memory.wiki.schema import ensure_schema
from synapse_memory.wiki.watermark import load_watermark, save_watermark


@dataclass
class IngestResult:
    source: str
    docs_processed: int = 0
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


def ingest_source(
    source: str,
    *,
    vault_path: Path | None = None,
    raw_root: Path | None = None,
    watermark_path: Path | None = None,
    ai_env: object | None = None,
    model: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    today: str | None = None,
    min_age_seconds: float | None = None,
    checkpoint_each: bool = False,
) -> IngestResult:
    """source의 새 RawDoc을 ingest. dry_run이면 적용/watermark/로그 생략.

    ``min_age_seconds``는 settled 필터로 ``iter_new_raw``에 그대로 전달된다.

    ``checkpoint_each``가 True면 doc 처리가 성공할 때마다 watermark를 저장해
    중단 후 재실행 시 남은 doc부터 이어 처리한다(재개 가능). 예외가 난 doc은
    watermark를 전진시키지 않으므로 재실행 시 재시도된다.
    """
    since = load_watermark(source, path=watermark_path)
    docs_all = iter_new_raw(
        source, since=since, root=raw_root, min_age_seconds=min_age_seconds
    )
    # 020: limit는 islice로 — 사이클당 doc 상한(메모리 천장). limit 없으면 전체.
    docs = islice(docs_all, limit) if limit is not None else docs_all

    result = IngestResult(source=source)
    # SCHEMA.md(wiki의 CLAUDE.md) 보장 — 어떤 에이전트든 wiki 유지 규약을 읽을 수
    # 있도록. ensure_schema는 idempotent(존재 시 보존). dry_run이면 디스크 미변경.
    if not dry_run:
        ensure_schema(vault_path=vault_path)
    # 020: 관련 페이지 선별용 전체 페이지를 사이클 1회 로드 — doc마다 재읽기 제거.
    all_pages = _all_pages(vault_path)
    max_mtime = since
    for doc in docs:
        result.docs_processed += 1
        try:
            related = find_related_pages(
                doc.text, vault_path=vault_path, pages=all_pages
            )
            prompt = build_integration_prompt(doc.text, related)
            payload = ai_api.complete_structured(
                prompt, system=INTEGRATION_SYSTEM, model=model,
                json_schema=INTEGRATION_SCHEMA, env=ai_env, timeout=120,
            )
            ops = _stamp_sources(parse_ops(payload), doc.ref)
            if dry_run:
                # dry-run은 디스크에 아무것도 쓰지 않으며 pages_written도 비워 둔다
                # (계획서 테스트 계약: result.pages_written == []).
                continue
            written = apply_ops(ops, vault_path=vault_path, today=today)
            result.pages_written.extend(written)
            # 020: 벡터 인덱싱 제거 — provider-only 검색(LLM-as-retriever). 로컬
            # 임베딩(bge-m3) 로드를 핫패스에서 영구 차단. 페이지는 디스크에만 기록.
            if written:
                append_log(
                    f"ingest {source}: {len(written)} pages "
                    f"({', '.join(written)}) from {doc.ref}",
                    vault_path=vault_path,
                )
        except Exception as exc:
            # 실패한 doc은 watermark를 전진시키지 않는다 → 재실행 시 재시도.
            result.errors.append(f"{doc.ref}: {exc}")
            continue
        # 성공 경로에서만 watermark 후보를 전진시킨다.
        if max_mtime is None or doc.mtime_iso > max_mtime:
            max_mtime = doc.mtime_iso
        if checkpoint_each and not dry_run and max_mtime:
            save_watermark(source, max_mtime, path=watermark_path)

    if not dry_run and max_mtime and max_mtime != since:
        save_watermark(source, max_mtime, path=watermark_path)
    return result
