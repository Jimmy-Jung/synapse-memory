# Tasks: Daily Resilience

**Input**: Design documents from `/specs/005-daily-resilience/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required by project constitution. Each behavior task has a RED test task before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create daily resilience scaffolding without changing behavior.

- [X] T001 [P] Create `tests/test_daily_cli.py` with module docstring and CLI runner helpers
- [X] T002 [P] Add DailyReport fixture helpers to `tests/test_daily.py`
- [X] T003 [P] Create `.github/workflows/ci.yml` shell with checkout/setup-python steps

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core stage model and result types used by all stories.

- [X] T004 [P] Write failing `DailyStage` validation/order tests in `tests/test_daily.py`
- [X] T005 [P] Write failing `StageResult` status property tests in `tests/test_daily.py`
- [X] T006 Implement `DailyStage`, `StageStatus`, and extended `StepResult` in `src/synapse_memory/daily.py`
- [X] T007 Implement stage registry validation helper in `src/synapse_memory/daily.py`
- [X] T008 Run foundational tests with `python3 -m pytest tests/test_daily.py -q`

**Checkpoint**: Stage metadata and result objects are deterministic and testable.

---

## Phase 3: User Story 1 - 실패 단계와 의존 단계가 명확히 보이는 daily 실행 (Priority: P1) MVP

**Goal**: A failed stage marks dependent stages skipped and keeps stdout/report-ready status for every selected stage.

**Independent Test**: Force classify failure with mocked stages and verify failed/skipped statuses plus exit semantics.

### Tests for User Story 1

- [X] T009 [P] [US1] Write failing dependency skip test for classify failure in `tests/test_daily.py`
- [X] T010 [P] [US1] Write failing skip reason test for downstream stages in `tests/test_daily.py`
- [X] T011 [P] [US1] Write failing CLI summary status test in `tests/test_daily_cli.py`

### Implementation for User Story 1

- [X] T012 [US1] Refactor `run_daily()` to iterate `DailyStage` registry in `src/synapse_memory/daily.py`
- [X] T013 [US1] Implement upstream failure skip logic in `src/synapse_memory/daily.py`
- [X] T014 [US1] Update `cmd_daily()` summary output for success/failed/skipped in `src/synapse_memory/cli.py`
- [X] T015 [US1] Run US1 tests with `python3 -m pytest tests/test_daily.py tests/test_daily_cli.py -q`

**Checkpoint**: User Story 1 is independently usable as the MVP.

---

## Phase 4: User Story 2 - 실패 지점부터 안전하게 재개하기 (Priority: P2)

**Goal**: `daily --resume-from <stage>` starts at the requested stage and records earlier stages as resume skips.

**Independent Test**: `daily --resume-from classify` executes no earlier stage and exposes resume skip statuses.

### Tests for User Story 2

- [X] T016 [P] [US2] Write failing `run_daily(resume_from=\"classify\")` test in `tests/test_daily.py`
- [X] T017 [P] [US2] Write failing unknown resume stage test in `tests/test_daily.py`
- [X] T018 [P] [US2] Write failing CLI `--resume-from` exit code tests in `tests/test_daily_cli.py`
- [X] T019 [P] [US2] Write failing dry-run resume output test in `tests/test_daily.py`

### Implementation for User Story 2

- [X] T020 [US2] Add `resume_from` parameter and validation to `run_daily()` in `src/synapse_memory/daily.py`
- [X] T021 [US2] Add `--resume-from` argparse wiring in `src/synapse_memory/cli.py`
- [X] T022 [US2] Ensure invalid resume returns exit code 2 before execution in `src/synapse_memory/cli.py`
- [X] T023 [US2] Run US2 tests with `python3 -m pytest tests/test_daily.py tests/test_daily_cli.py -q`

**Checkpoint**: User Stories 1 and 2 work independently.

---

## Phase 5: User Story 3 - PR마다 자동 검증되는 CI (Priority: P3)

**Goal**: PR/main runs pytest, ruff, and mypy without local-only provider binaries.

**Independent Test**: Workflow file contains the required commands and does not require private secrets.

### Tests for User Story 3

- [X] T024 [P] [US3] Write failing workflow presence/trigger tests in `tests/test_daily_cli.py`
- [X] T025 [P] [US3] Write failing workflow command tests for pytest/ruff/mypy in `tests/test_daily_cli.py`

### Implementation for User Story 3

- [X] T026 [US3] Complete `.github/workflows/ci.yml` with pytest, ruff, and mypy jobs
- [X] T027 [US3] Run CI workflow structure tests with `python3 -m pytest tests/test_daily_cli.py -q`

**Checkpoint**: CI contract exists and is locally testable.

---

## Phase 6: DailyReport, Documentation, and Quality Gates

**Purpose**: Persist observability output, document usage, and run merge gates.

- [X] T028 [P] Write failing DailyReport render/no-raw-fields tests in `tests/test_daily.py`
- [X] T029 Implement DailyReport markdown rendering and write helper in `src/synapse_memory/daily.py`
- [X] T030 Integrate report stage into daily stage registry in `src/synapse_memory/daily.py`
- [X] T031 [P] Update `docs/commands.md` daily section with `--resume-from`, skip semantics, and report path
- [X] T032 [P] Update `commands/synapse-daily.md` with `--resume-from` examples and `SYNAPSE_FROM_AGENT=1`
- [X] T033 Run quickstart smoke from `specs/005-daily-resilience/quickstart.md` and save transcript in `specs/005-daily-resilience/quickstart-results.md`
- [X] T034 Run ruff on changed files with `uvx ruff check src/synapse_memory/daily.py src/synapse_memory/cli.py tests/test_daily.py tests/test_daily_cli.py`
- [X] T035 Run mypy strict with `python3 -m mypy --strict src/synapse_memory/daily.py`
- [X] T036 Run full tests with `python3 -m pytest tests/ -W ignore::DeprecationWarning`
- [X] T037 Run redaction golden eval and record Pass1/Pass2 F1 in `specs/005-daily-resilience/redaction-eval-results.md`
- [X] T038 Review `git diff --check` and remove unrelated changes before commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1; blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2; MVP.
- **Phase 4 US2**: Depends on Phase 2 and benefits from US1 output semantics.
- **Phase 5 US3**: Independent after Phase 1, but implementation can wait until daily tests stabilize.
- **Phase 6 Polish**: Depends on selected user stories.

### MVP Scope

Complete Phase 1, Phase 2, and Phase 3. This delivers failure isolation and dependency-aware skip behavior before resume/report polish.

### Parallel Opportunities

- T001-T003 can run in parallel.
- T004-T005 can run in parallel before T006-T007.
- US1 tests T009-T011 can run in parallel.
- US2 tests T016-T019 can run in parallel.
- CI tests T024-T025 can run in parallel.
- Documentation tasks T031-T032 can run in parallel after CLI shape stabilizes.

## Parallel Examples

```bash
# US1 tests can be drafted together:
Task: "Write failing dependency skip test for classify failure in tests/test_daily.py"
Task: "Write failing CLI summary status test in tests/test_daily_cli.py"
```

```bash
# US2 tests can be drafted together:
Task: "Write failing run_daily resume_from test in tests/test_daily.py"
Task: "Write failing CLI --resume-from exit code tests in tests/test_daily_cli.py"
```

## Implementation Strategy

1. Build stage metadata and result model first.
2. Deliver MVP skip behavior for upstream failures.
3. Add resume semantics and CLI validation.
4. Add CI workflow contract.
5. Add DailyReport persistence, docs, quickstart, and quality gates.
