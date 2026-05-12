# Tasks: Recipe Hybrid Retrieval

**Input**: Design documents from `specs/008-recipe-hybrid-retrieval/`  
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Required by Constitution Principle III. Every behavior change starts with RED tests.

**Organization**: Tasks are grouped by user story so each story can be implemented and reviewed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: User story label (`US1`, `US2`, `US3`)
- Every task includes exact file paths

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the branch has the upstream hybrid dependency and active spec context.

- [ ] T001 Verify `006-raw-rag-hybrid` artifacts are available in the implementation branch: `src/synapse_memory/rag/hybrid.py`, `src/synapse_memory/rag/bm25.py`, `tests/test_rag_hybrid.py`
- [ ] T002 If T001 fails, merge/rebase onto `006-raw-rag-hybrid` or wait until 006 lands on `main`; do not reimplement 006 inside `specs/008-recipe-hybrid-retrieval/`
- [ ] T003 Verify active Spec Kit markers point to `specs/008-recipe-hybrid-retrieval/plan.md` in `AGENTS.md` and `CLAUDE.md`
- [ ] T004 [P] Review existing dense recipe tests in `tests/test_recipes_pipeline.py`, `tests/test_recipes_cli.py`, and `tests/test_recipes_loader.py` before adding new tests

**Checkpoint**: Upstream hybrid dependency and active feature context are clear.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared retrieval-mode model and validation before user story behavior.

**CRITICAL**: No user story implementation begins until this phase is complete.

### Tests First

- [ ] T005 [P] Write RED loader test for valid `rag_mode: dense` and `rag_mode: hybrid` in `tests/test_recipes_loader.py`
- [ ] T006 [P] Write RED loader test for missing `rag_mode` defaulting to dense in `tests/test_recipes_loader.py`
- [ ] T007 [P] Write RED loader test for invalid `rag_mode` isolated recipe rejection in `tests/test_recipes_loader.py`
- [ ] T008 [P] Write RED dataclass/context assertions for `GenerationRecipe.rag_mode` and `GenerationContext.rag_mode` in `tests/test_recipes_pipeline.py`

### Implementation

- [ ] T009 Add `RecipeRagMode = Literal["dense", "hybrid"]` and `rag_mode` fields to `src/synapse_memory/recipes/recipe.py`
- [ ] T010 Extend frontmatter parsing and validation for `rag_mode` in `src/synapse_memory/recipes/loader.py`
- [ ] T011 Update any built-in recipe fixtures only if needed for explicit dense defaults in `src/synapse_memory/recipes/builtin/*.md`
- [ ] T012 Run `python3 -m pytest tests/test_recipes_loader.py tests/test_recipes_pipeline.py -q`
- [ ] T013 Commit Phase 2 changes with Conventional Commit message

**Checkpoint**: Recipe model can represent retrieval mode without changing behavior.

---

## Phase 3: User Story 1 - Recipe가 hybrid retrieval을 선택한다 (Priority: P1) MVP

**Goal**: A recipe with `rag_mode: hybrid` uses 006 hybrid retrieval and still feeds the existing recipe pipeline downstream shape.

**Independent Test**: A fixture recipe with `rag_mode: hybrid` calls `hybrid_search`, prompt composition receives matched records, and dense-default recipes remain unchanged.

### Tests for User Story 1

- [ ] T014 [P] [US1] Write RED pipeline test that `rag_mode: hybrid` calls `synapse_memory.rag.hybrid.hybrid_search` in `tests/test_recipes_pipeline.py`
- [ ] T015 [P] [US1] Write RED pipeline test that hybrid `RetrievalHit` values are adapted to matched records with metadata/source ids in `tests/test_recipes_pipeline.py`
- [ ] T016 [P] [US1] Write RED regression test proving missing `rag_mode` still uses dense `store.query` in `tests/test_recipes_pipeline.py`
- [ ] T017 [P] [US1] Write RED domain-aware hybrid fixture test using matched record tags in `tests/test_recipes_domain.py`
- [ ] T018 [P] [US1] Write RED prompt-capture test proving hybrid matched records enter the user prompt without raw unredacted markers in `tests/test_recipes_generate.py`

### Implementation for User Story 1

- [ ] T019 [US1] Add retrieval-mode resolution helper in `src/synapse_memory/recipes/pipeline.py`
- [ ] T020 [US1] Add dense query builder reuse for both dense and hybrid paths in `src/synapse_memory/recipes/pipeline.py`
- [ ] T021 [US1] Call 006 `hybrid_search` when effective mode is hybrid in `src/synapse_memory/recipes/pipeline.py`
- [ ] T022 [US1] Add adapter from 006 `RetrievalHit` to existing matched-record tuples in `src/synapse_memory/recipes/pipeline.py`
- [ ] T023 [US1] Preserve source ids, `last_answer`, prompt citation metadata, and tag metadata in `src/synapse_memory/recipes/pipeline.py`
- [ ] T024 [US1] Add `rag_mode` to `GenerationContext` and returned `GenerationResult` if needed for observability in `src/synapse_memory/recipes/recipe.py`
- [ ] T025 [US1] Run `python3 -m pytest tests/test_recipes_pipeline.py tests/test_recipes_domain.py tests/test_recipes_generate.py -q`
- [ ] T026 [US1] Commit Phase 3 changes with Conventional Commit message

**Checkpoint**: Hybrid recipe MVP is fully testable independent of CLI override.

---

## Phase 4: User Story 2 - CLI에서 recipe 기본 retrieval mode를 override한다 (Priority: P2)

**Goal**: `--rag-mode dense|hybrid` overrides recipe frontmatter for one invocation.

**Independent Test**: CLI tests prove dense-to-hybrid and hybrid-to-dense overrides without modifying recipe files.

### Tests for User Story 2

- [ ] T027 [P] [US2] Write RED parser test for `me generate <recipe> --rag-mode hybrid` in `tests/test_recipes_cli.py`
- [ ] T028 [P] [US2] Write RED CLI test proving `--rag-mode hybrid` overrides a dense recipe in `tests/test_recipes_cli.py`
- [ ] T029 [P] [US2] Write RED CLI test proving `--rag-mode dense` overrides a hybrid recipe in `tests/test_recipes_cli.py`
- [ ] T030 [P] [US2] Write RED CLI invalid-choice test for `--rag-mode invalid` in `tests/test_recipes_cli.py`

### Implementation for User Story 2

- [ ] T031 [US2] Add argparse `--rag-mode {dense,hybrid}` to `me generate` in `src/synapse_memory/cli.py`
- [ ] T032 [US2] Pass CLI override into `recipes_generate()` from `src/synapse_memory/cli.py`
- [ ] T033 [US2] Add library-level `rag_mode_override` argument to `generate()` in `src/synapse_memory/recipes/pipeline.py`
- [ ] T034 [US2] Ensure override is not written back to recipe markdown in `src/synapse_memory/recipes/pipeline.py`
- [ ] T035 [US2] Run `python3 -m pytest tests/test_recipes_cli.py tests/test_recipes_pipeline.py -q`
- [ ] T036 [US2] Commit Phase 4 changes with Conventional Commit message

**Checkpoint**: Users can compare dense and hybrid behavior without editing recipes.

---

## Phase 5: User Story 3 - Hybrid 미가용 상태를 명확히 보고한다 (Priority: P3)

**Goal**: Missing BM25 sidecar or hybrid dependency fails explicitly and never claims dense fallback as hybrid.

**Independent Test**: Isolated L0 with no sidecar produces non-zero CLI result and remediation text.

### Tests for User Story 3

- [ ] T037 [P] [US3] Write RED pipeline test that missing BM25 sidecar raises a recipe-level hybrid availability error in `tests/test_recipes_pipeline.py`
- [ ] T038 [P] [US3] Write RED CLI test that hybrid-unavailable stderr includes `synapse-memory rag index --include-raw` in `tests/test_recipes_cli.py`
- [ ] T039 [P] [US3] Write RED test proving hybrid-unavailable does not call dense fallback after failure in `tests/test_recipes_pipeline.py`
- [ ] T040 [P] [US3] Write RED regression test keeping `me what-did-i-think --timeline` outside recipe pipeline in `tests/test_endpoints_me_extra.py`

### Implementation for User Story 3

- [ ] T041 [US3] Define `RecipeHybridUnavailableError` or equivalent user-facing error in `src/synapse_memory/recipes/pipeline.py`
- [ ] T042 [US3] Catch 006 BM25/hybrid availability errors and re-raise with remediation text in `src/synapse_memory/recipes/pipeline.py`
- [ ] T043 [US3] Map hybrid availability errors to non-zero CLI stderr in `src/synapse_memory/cli.py`
- [ ] T044 [US3] Ensure dense fallback is not executed after hybrid path selection in `src/synapse_memory/recipes/pipeline.py`
- [ ] T045 [US3] Run `python3 -m pytest tests/test_recipes_pipeline.py tests/test_recipes_cli.py tests/test_endpoints_me_extra.py -q`
- [ ] T046 [US3] Commit Phase 5 changes with Conventional Commit message

**Checkpoint**: Hybrid readiness failures are honest, actionable, and regression-covered.

---

## Phase 6: Documentation, Observability, and Acceptance

**Purpose**: Update user/developer docs, quickstart, and final regression gates.

- [ ] T047 [P] Document `rag_mode` frontmatter and `--rag-mode` in `docs/commands.md`
- [ ] T048 [P] Document recipe retrieval mode architecture in `docs/architecture.md`
- [ ] T049 [P] Add `rag_mode=<dense|hybrid>` interpretation to `docs/development.md`
- [ ] T050 [P] Update `specs/008-recipe-hybrid-retrieval/quickstart.md` after actual smoke output is known
- [ ] T051 Add `rag_mode=<mode>` to `me.generate.<recipe>` stderr observability in `src/synapse_memory/cli.py`
- [ ] T052 Run quickstart smoke on an isolated fixture vault and capture results in `specs/008-recipe-hybrid-retrieval/quickstart-results.md`
- [ ] T053 Run `python3 -m pytest tests/test_endpoints_me.py tests/test_endpoints_me_extra.py -q`
- [ ] T054 Run `python3 -m pytest tests/test_recipes_loader.py tests/test_recipes_registry.py tests/test_recipes_locale.py tests/test_recipes_domain.py tests/test_recipes_pipeline.py tests/test_recipes_generate.py tests/test_recipes_cli.py tests/test_recipes_sc_acceptance.py -q`
- [ ] T055 Run `python3 -m pytest`
- [ ] T056 Run `git diff --check`
- [ ] T057 Review diff for redaction boundary and no Co-Authored-By lines before final commit
- [ ] T058 Commit Phase 6 changes with Conventional Commit message

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies, but must confirm 006 availability before code work.
- **Phase 2 Foundational**: Depends on Setup; blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2; MVP.
- **Phase 4 US2**: Depends on Phase 3 retrieval-mode resolution, but CLI parser test can be drafted earlier.
- **Phase 5 US3**: Depends on Phase 3 hybrid path and 006 error types.
- **Phase 6 Polish**: Depends on selected user stories complete.

### User Story Dependencies

- **US1**: MVP, required before CLI override has meaningful behavior.
- **US2**: Builds on US1 and can be reviewed separately.
- **US3**: Builds on US1 and should land before final acceptance.

### Parallel Opportunities

- T005-T008 can be written in parallel.
- T014-T018 can be written in parallel after Phase 2.
- T027-T030 can be written in parallel after CLI contract review.
- T037-T040 can be written in parallel after hybrid path shape is known.
- T047-T050 can be drafted in parallel after implementation behavior settles.

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 only.
3. Validate that a recipe frontmatter `rag_mode: hybrid` works independently.
4. Stop for review before adding CLI override if needed.

### Incremental Delivery

1. Phase 3: recipe opt-in hybrid.
2. Phase 4: CLI override.
3. Phase 5: explicit unavailable errors.
4. Phase 6: docs, smoke, full regression.

### Commit Strategy

- Commit after each phase as requested.
- Use Conventional Commit subject and Korean body.
- Do not push without user confirmation.
