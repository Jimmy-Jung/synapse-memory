# Tasks: Raw RAG Hybrid

**Input**: Design documents from `/specs/006-raw-rag-hybrid/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required by project constitution. Each behavior task has a RED test task before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create scaffolding for raw chunking and hybrid retrieval without changing existing dense-only behavior.

- [X] T001 [P] Create `tests/test_rag_chunker.py` with raw chunk fixture helpers
- [X] T002 [P] Create `tests/test_rag_bm25.py` with sidecar temp-dir helpers
- [X] T003 [P] Create `tests/test_rag_hybrid.py` with deterministic VectorRecord fixtures
- [X] T004 [P] Add `tests/golden/raw_rag_hybrid/synthetic_queries.json` synthetic eval fixture
- [X] T005 [P] Create placeholder modules `src/synapse_memory/rag/chunker.py`, `src/synapse_memory/rag/bm25.py`, and `src/synapse_memory/rag/hybrid.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Deterministic chunk, BM25 sidecar, and RRF primitives used by all stories.

- [X] T006 [P] Write failing chunk window/overlap determinism tests in `tests/test_rag_chunker.py`
- [X] T007 [P] Write failing raw source discovery tests for vault `10_Active/` and L0 `redacted/claude-code/` in `tests/test_rag_chunker.py`
- [X] T008 Implement `RawChunk`, `tokenize_text()`, `chunk_text()`, and source discovery in `src/synapse_memory/rag/chunker.py`
- [X] T009 [P] Write failing BM25 tokenize/write/read/search tests in `tests/test_rag_bm25.py`
- [X] T010 Implement `BM25Document`, sidecar persistence, and BM25 search in `src/synapse_memory/rag/bm25.py`
- [X] T011 [P] Write failing RRF merge/tie-break tests in `tests/test_rag_hybrid.py`
- [X] T012 Implement `RetrievalHit`, `reciprocal_rank_fusion()`, and merge helpers in `src/synapse_memory/rag/hybrid.py`
- [X] T013 Export new RAG helpers from `src/synapse_memory/rag/__init__.py`
- [X] T014 Run foundational tests with `python3 -m pytest tests/test_rag_chunker.py tests/test_rag_bm25.py tests/test_rag_hybrid.py -q`

**Checkpoint**: Raw chunks, BM25 sidecar, and RRF can be tested without ChromaDB or external AI.

---

## Phase 3: User Story 1 - Card가 아닌 raw 노트도 검색 근거로 쓰기 (Priority: P1) MVP

**Goal**: `rag index --include-raw` indexes redacted raw chunks with stable ids and metadata.

**Independent Test**: Index fixture vault + L0 redacted Claude Code files with mocked embeddings and captured vector records.

### Tests for User Story 1

- [X] T015 [P] [US1] Write failing `include_raw` index stats test in `tests/test_rag_indexer.py`
- [X] T016 [P] [US1] Write failing raw metadata/id stability test in `tests/test_rag_indexer.py`
- [X] T017 [P] [US1] Write failing raw redaction-before-upsert test in `tests/test_rag_indexer.py`
- [X] T018 [P] [US1] Write failing CLI `rag index --include-raw` output test in `tests/test_rag_cli.py`

### Implementation for User Story 1

- [X] T019 [US1] Extend `IndexStats` with raw/BM25 counters in `src/synapse_memory/rag/indexer.py`
- [X] T020 [US1] Add `include_raw` parameter and raw chunk record creation to `index_cards()` in `src/synapse_memory/rag/indexer.py`
- [X] T021 [US1] Write BM25 sidecar documents during raw/Card indexing in `src/synapse_memory/rag/indexer.py`
- [X] T022 [US1] Add `--include-raw` argparse wiring and count output in `src/synapse_memory/cli.py`
- [X] T023 [US1] Run US1 tests with `python3 -m pytest tests/test_rag_indexer.py tests/test_rag_cli.py -q`

**Checkpoint**: User Story 1 is independently usable as the MVP.

---

## Phase 4: User Story 2 - 고유명사 검색에서 hybrid ranking 쓰기 (Priority: P2)

**Goal**: `ask --hybrid` and `me what-did-i-think --hybrid` use dense + BM25 RRF retrieval.

**Independent Test**: Synthetic proper-noun fixture ranks exact-match records above dense-only order.

### Tests for User Story 2

- [X] T024 [P] [US2] Write failing hybrid search integration test in `tests/test_rag_hybrid.py`
- [X] T025 [P] [US2] Write failing `ask(hybrid=True)` retrieval order test in `tests/test_endpoints_ask.py`
- [X] T026 [P] [US2] Write failing `what_did_i_think(hybrid=True)` retrieval order test in `tests/test_endpoints_me_extra.py`
- [X] T027 [P] [US2] Write failing CLI flag tests for `ask --hybrid` and `me what-did-i-think --hybrid` in CLI tests
- [X] T028 [P] [US2] Write failing missing BM25 sidecar error test in `tests/test_endpoints_ask.py`

### Implementation for User Story 2

- [X] T029 [US2] Implement `hybrid_search()` orchestration in `src/synapse_memory/rag/hybrid.py`
- [X] T030 [US2] Add `hybrid` parameter to `ask()` and route retrieval through hybrid search in `src/synapse_memory/endpoints/ask.py`
- [X] T031 [US2] Add `hybrid` parameter to `what_did_i_think()` distance mode in `src/synapse_memory/endpoints/me.py`
- [X] T032 [US2] Add `--hybrid` argparse wiring and invalid `--timeline --hybrid` handling in `src/synapse_memory/cli.py`
- [X] T033 [US2] Update source citation formatting for RRF/BM25/raw details in `src/synapse_memory/endpoints/ask.py`, `src/synapse_memory/endpoints/me.py`, and `src/synapse_memory/cli.py`
- [X] T034 [US2] Run US2 tests with `python3 -m pytest tests/test_rag_hybrid.py tests/test_endpoints_ask.py tests/test_endpoints_me_extra.py tests/test_rag_cli.py -q`

**Checkpoint**: User Stories 1 and 2 work independently.

---

## Phase 5: User Story 3 - raw가 외부 LLM으로 새지 않는 retrieval 안전망 (Priority: P3)

**Goal**: Raw-backed retrieval never sends unredacted raw markers to external AI providers.

**Independent Test**: Capture AI provider prompt for raw-backed hybrid answer and assert original synthetic marker is absent.

### Tests for User Story 3

- [X] T035 [P] [US3] Write failing `ask --hybrid` no-raw-prompt test in `tests/test_endpoints_ask.py`
- [X] T036 [P] [US3] Write failing `me what-did-i-think --hybrid` no-raw-prompt test in `tests/test_endpoints_me_extra.py`
- [X] T037 [P] [US3] Write failing BM25 sidecar prohibited raw fields test in `tests/test_rag_bm25.py`

### Implementation for User Story 3

- [X] T038 [US3] Ensure raw prompt context uses only redacted `VectorRecord.document` in `src/synapse_memory/endpoints/ask.py` and `src/synapse_memory/endpoints/me.py`
- [X] T039 [US3] Add sidecar validation that rejects prohibited raw fields/content in `src/synapse_memory/rag/bm25.py`
- [X] T040 [US3] Run US3 tests with `python3 -m pytest tests/test_endpoints_ask.py tests/test_endpoints_me_extra.py tests/test_rag_bm25.py -q`

**Checkpoint**: Raw RAG privacy invariant is covered by tests.

---

## Phase 6: Eval, Documentation, and Quality Gates

**Purpose**: Record retrieval/redaction evidence and update user-facing docs.

- [X] T041 [P] Add synthetic NDCG/top-1 eval helper or deterministic test assertions for `tests/golden/raw_rag_hybrid/synthetic_queries.json`
- [X] T042 [P] Update `docs/commands.md` with `rag index --include-raw`, `ask --hybrid`, and `me what-did-i-think --hybrid`
- [X] T043 [P] Update slash command docs in `commands/` for affected commands
- [ ] T044 Run quickstart smoke from `specs/006-raw-rag-hybrid/quickstart.md` and save transcript in `specs/006-raw-rag-hybrid/quickstart-results.md`
- [X] T045 Run scoped ruff on changed files
- [X] T046 Run mypy strict on changed RAG/endpoints modules
- [X] T047 Run full tests with `python3 -m pytest tests/ -W ignore::DeprecationWarning`
- [X] T048 Run redaction golden eval and record Pass1/Pass2 F1 in `specs/006-raw-rag-hybrid/redaction-eval-results.md`
- [X] T049 Review `git diff --check` and remove unrelated changes before commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1; blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2; MVP.
- **Phase 4 US2**: Depends on Phase 2 and benefits from US1 sidecar/index output.
- **Phase 5 US3**: Depends on US1/US2 prompt paths.
- **Phase 6 Polish**: Depends on selected user stories.

### MVP Scope

Complete Phase 1, Phase 2, and Phase 3. This delivers raw chunk indexing before hybrid endpoint behavior.

### Parallel Opportunities

- T001-T005 can run in parallel.
- T006-T007, T009, and T011 can run in parallel before implementation.
- US1 tests T015-T018 can run in parallel.
- US2 tests T024-T028 can run in parallel after foundational helpers exist.
- Documentation tasks T042-T043 can run in parallel after CLI shape stabilizes.

## Implementation Strategy

1. Build deterministic chunking, BM25 sidecar, and RRF helpers first.
2. Deliver `rag index --include-raw` as the MVP.
3. Add hybrid retrieval to `ask` and `me what-did-i-think`.
4. Add prompt/privacy regression tests.
5. Record retrieval eval, redaction eval, docs, and quality gates.
