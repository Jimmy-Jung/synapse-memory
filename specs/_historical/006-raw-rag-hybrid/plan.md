# Implementation Plan: Raw RAG Hybrid

> **SUPERSEDED_BY_PROVIDER_ONLY / HISTORICAL ONLY**
>
> 이 문서는 provider-only 전환 전의 과거 구현 계획입니다. 현재 구현은 local
> embeddings/vector/BM25/hybrid ranking을 쓰지 않고 provider 선별로 일원화되어 있습니다.
> 현재 source of truth는 `specs/020-provider-only-retrieval/design.md`입니다.

**Branch**: `006-raw-rag-hybrid` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/006-raw-rag-hybrid/spec.md`

## Summary

Synapse Memory의 RAG 검색 범위를 Card-only에서 redacted raw chunks까지 확장하고, `ask --hybrid` 및 `me what-did-i-think --hybrid`에서 dense vector 결과와 BM25 keyword 결과를 RRF(k=60)로 결합한다. Raw source는 인덱싱 전에 redaction을 통과시켜 vector/BM25 sidecar와 외부 AI prompt 모두 redacted 텍스트만 다루게 한다.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: 기존 `chromadb`, `sentence-transformers`, `rank-bm25`, `pytest`, `ruff`, `mypy`  
**Storage**: `~/.synapse/private/rag/chroma/`, 신규 `~/.synapse/private/rag/bm25.jsonl`, vault `10_Active/`, `~/.synapse/private/redacted/claude-code/`  
**Testing**: pytest, ruff, mypy strict, retrieval eval fixtures, redaction golden eval  
**Target Platform**: macOS 26 Tahoe + Apple Silicon  
**Project Type**: Python CLI/library  
**Performance Goals**: chunking 1MB markdown ≤ 500ms, BM25 sidecar load ≤ 300ms for 5k docs, hybrid retrieve p95 ≤ 4s excluding external AI call  
**Constraints**: raw external payload 금지, deterministic ids, backward-compatible dense-only behavior, no new cloud dependency, test-first implementation  
**Scale/Scope**: single-user local index, hundreds of Cards, thousands of raw chunks, top-k 5~20 retrieval

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 계획상 준수 방식 | 위험 / 완화 |
|---|---|---|
| I. Local-First & Privacy by Default | raw source는 local filesystem에서 읽고 vector/BM25 index도 L0 아래에만 저장한다. | Obsidian `10_Active` 원문이 index에 저장될 위험 → raw chunk는 redaction 후 저장하고 테스트로 원문 marker 부재를 검증한다. |
| II. Two-Pass Redaction | raw chunk text는 `redact_full()` 경로를 통해 redacted document로 변환한 뒤 upsert/sidecar/prompt에 사용한다. | Pass2 local model unavailable 시 raw를 우회 저장할 위험 → 실패를 명시 오류로 처리하고 raw indexing을 중단한다. |
| III. Test-First Discipline | chunker, raw indexer, BM25, RRF, endpoint flags, no-raw prompt 테스트를 구현 전 tasks에 배치한다. | retrieval eval은 synthetic일 수 있음 → synthetic 한계를 docs에 명시하고 deterministic fixture로 회귀 가드를 둔다. |
| IV. Conversation-Context-Aware Endpoints | `ask`와 `me what-did-i-think`는 기존 interactive guard를 유지하고, `rag index/search`는 batch로 유지한다. | `--hybrid` 오류가 prompt로 바뀌면 automation break → CLI는 명확한 exit code와 stderr를 반환한다. |
| V. Reproducible Daily Pipeline & Observability | `daily`는 raw/hybrid 구현 대상이 아니며 기존 stage contract를 변경하지 않는다. | daily index stage가 `include_raw`를 기본 활성화하면 idempotence 영향 → 이번 feature는 CLI opt-in으로 유지한다. |

**게이트 결과 (사전)**: 통과. Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/006-raw-rag-hybrid/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-contracts.md
│   └── file-contracts.md
└── tasks.md
```

### Source Code (repository root)

```text
src/synapse_memory/
├── rag/
│   ├── chunker.py              # raw text split, source discovery helpers
│   ├── bm25.py                 # sidecar persistence + keyword ranking
│   ├── hybrid.py               # dense/BM25 RRF merge
│   ├── indexer.py              # --include-raw indexing path
│   ├── vector_store.py         # existing VectorRecord API reused
│   └── __init__.py             # public exports
├── endpoints/
│   ├── ask.py                  # hybrid retrieval and raw citations
│   └── me.py                   # what-did-i-think --hybrid distance mode
└── cli.py                      # rag/ask/me flags and output

tests/
├── test_rag_chunker.py
├── test_rag_bm25.py
├── test_rag_hybrid.py
├── test_rag_indexer.py
├── test_endpoints_ask.py
├── test_endpoints_me_extra.py
└── test_endpoints_me_timeline.py
```

**Structure Decision**: `rag/` 안에 raw chunking, BM25, hybrid merge를 분리한다. `indexer.py`는 Card와 raw를 vector store로 쓰는 orchestration layer로 확장하고, endpoint는 retrieval mode 선택과 prompt/citation formatting만 담당한다. BM25 sidecar는 ChromaDB 내부 구현에 기대지 않는 별도 JSONL 파일로 두어 테스트와 복구를 단순하게 한다.

## Phase 0 산출물

See [research.md](./research.md).

## Phase 1 산출물

- [data-model.md](./data-model.md)
- [contracts/cli-contracts.md](./contracts/cli-contracts.md)
- [contracts/file-contracts.md](./contracts/file-contracts.md)
- [quickstart.md](./quickstart.md)

## Constitution Check (post-design re-check)

| 원칙 | 재확인 결과 |
|---|---|
| I. Local-First & Privacy by Default | 통과. raw source와 sidecar 모두 local-only이며 raw text는 redacted document로만 저장한다. |
| II. Two-Pass Redaction | 통과. raw chunk indexing은 redaction 실패 시 중단하고 우회 저장하지 않는다. |
| III. Test-First Discipline | 통과. tasks에 RED 테스트를 구현 전 배치한다. |
| IV. Conversation-Context-Aware Endpoints | 통과. 기존 interactive/batch 분류를 유지한다. |
| V. Reproducible Daily Pipeline & Observability | 통과. daily 기본 동작은 변경하지 않는다. |

**최종 게이트 결과**: 통과. Complexity Tracking 불필요.

## Complexity Tracking

위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
