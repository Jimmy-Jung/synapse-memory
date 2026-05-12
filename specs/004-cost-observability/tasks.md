# Tasks: Cost Observability

**Input**: Design documents from `/specs/004-cost-observability/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required by project constitution. Each behavior task has a RED test task before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create cost observability scaffolding without behavior.

- [ ] T001 [P] Create cost package exports in `src/synapse_memory/cost/__init__.py`
- [ ] T002 [P] Create empty test modules `tests/test_cost_events.py`, `tests/test_cost_summary.py`, `tests/test_cost_cli.py`
- [ ] T003 [P] Create slash command doc shell in `commands/synapse-cost.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core cost event model, storage, and pricing helpers that all user stories depend on.

- [ ] T004 [P] Write failing CostEvent validation/no-raw-fields tests in `tests/test_cost_events.py`
- [ ] T005 [P] Write failing append-only/recovery/permission tests in `tests/test_cost_events.py`
- [ ] T006 Implement CostEvent dataclass, event id generation, and validation in `src/synapse_memory/cost/events.py`
- [ ] T007 Implement append-only JSONL writer, loader, and corrupt-tail recovery in `src/synapse_memory/cost/events.py`
- [ ] T008 [P] Write failing pricing fallback tests for provider/local/unknown models in `tests/test_cost_events.py`
- [ ] T009 Implement deterministic pricing helpers in `src/synapse_memory/cost/pricing.py`
- [ ] T010 Run foundational tests with `python3 -m pytest tests/test_cost_events.py -q`

**Checkpoint**: Cost events can be safely created, persisted, loaded, and recovered.

---

## Phase 3: User Story 1 - AI 호출 비용 자동 기록 (Priority: P1) MVP

**Goal**: Record one cost event after every Claude Code CLI or apfel subprocess call.

**Independent Test**: Mocked Claude/apfel calls append cost rows with provider/model/token/usd/elapsed/status and no prompt/response raw text.

### Tests for User Story 1

- [ ] T011 [P] [US1] Write failing Claude success cost logging tests in `tests/test_llm_claude.py`
- [ ] T012 [P] [US1] Write failing Claude error/timeout cost logging tests in `tests/test_llm_claude.py`
- [ ] T013 [P] [US1] Write failing apfel success cost logging tests in `tests/test_apfel.py`
- [ ] T014 [P] [US1] Write failing apfel error/timeout cost logging tests in `tests/test_apfel.py`
- [ ] T015 [P] [US1] Write failing command context tests for `SYNAPSE_COMMAND` fallback in `tests/test_cost_events.py`

### Implementation for User Story 1

- [ ] T016 [US1] Add command context resolver in `src/synapse_memory/cost/events.py`
- [ ] T017 [US1] Extract Claude envelope token/cost metadata in `src/synapse_memory/llm/claude.py`
- [ ] T018 [US1] Record Claude success/error/timeout cost events in `src/synapse_memory/llm/claude.py`
- [ ] T019 [US1] Record apfel success/error/timeout cost events in `src/synapse_memory/llm/apfel.py`
- [ ] T020 [US1] Ensure cost logging failures do not change original Claude/apfel behavior in `src/synapse_memory/llm/claude.py` and `src/synapse_memory/llm/apfel.py`
- [ ] T021 [US1] Run US1 tests with `python3 -m pytest tests/test_llm_claude.py tests/test_apfel.py tests/test_cost_events.py -q`

**Checkpoint**: User Story 1 is independently usable as the MVP.

---

## Phase 4: User Story 2 - 최근 비용 요약 보기 (Priority: P2)

**Goal**: Summarize recent cost events by command or model in table or JSON form.

**Independent Test**: A mixed fixture with several dates, commands, and models aggregates correctly for `--days`, `--by`, and `--json`.

### Tests for User Story 2

- [ ] T022 [P] [US2] Write failing summary date filtering and command grouping tests in `tests/test_cost_summary.py`
- [ ] T023 [P] [US2] Write failing summary model grouping and total row tests in `tests/test_cost_summary.py`
- [ ] T024 [P] [US2] Write failing JSON output parse/no-table tests in `tests/test_cost_cli.py`
- [ ] T025 [P] [US2] Write failing no-data and invalid-days CLI tests in `tests/test_cost_cli.py`

### Implementation for User Story 2

- [ ] T026 [US2] Implement CostSummaryGroup and aggregation in `src/synapse_memory/cost/summary.py`
- [ ] T027 [US2] Implement table and JSON render helpers in `src/synapse_memory/cost/summary.py`
- [ ] T028 [US2] Add `cost summary` argparse wiring and handler in `src/synapse_memory/cli.py`
- [ ] T029 [US2] Add command context assignment for CLI command families in `src/synapse_memory/cli.py`
- [ ] T030 [US2] Run US2 tests with `python3 -m pytest tests/test_cost_summary.py tests/test_cost_cli.py -q`

**Checkpoint**: User Stories 1 and 2 work independently.

---

## Phase 5: User Story 3 - 비용 로그를 안전하게 운영하기 (Priority: P3)

**Goal**: Keep cost logging private, recoverable, and safe for daily/report usage.

**Independent Test**: Corrupt-tail recovery preserves readable prefix events, creates a backup, and never persists prohibited raw fields.

### Tests for User Story 3

- [ ] T031 [P] [US3] Write failing prohibited-field regression tests in `tests/test_cost_events.py`
- [ ] T032 [P] [US3] Write failing summary corrupt-tail recovery tests in `tests/test_cost_summary.py`
- [ ] T033 [P] [US3] Write failing private permission tests for first-write behavior in `tests/test_cost_events.py`
- [ ] T034 [P] [US3] Write failing logging-warning isolation tests in `tests/test_llm_claude.py` and `tests/test_apfel.py`

### Implementation for User Story 3

- [ ] T035 [US3] Harden CostEvent serialization against prohibited keys in `src/synapse_memory/cost/events.py`
- [ ] T036 [US3] Ensure summary loads with recovery enabled and reports backup warnings in `src/synapse_memory/cost/summary.py`
- [ ] T037 [US3] Ensure first-write directory/file permissions use L0 helpers in `src/synapse_memory/cost/events.py`
- [ ] T038 [US3] Route logging failure warnings to stderr without swallowing original provider exceptions in `src/synapse_memory/llm/claude.py` and `src/synapse_memory/llm/apfel.py`
- [ ] T039 [US3] Run US3 tests with `python3 -m pytest tests/test_cost_events.py tests/test_cost_summary.py tests/test_llm_claude.py tests/test_apfel.py -q`

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Documentation, Quality Gates, and Release Prep

**Purpose**: User-facing docs, compatibility command, and merge gates.

- [ ] T040 [P] Document `cost summary` options and examples in `docs/commands.md`
- [ ] T041 [P] Complete `commands/synapse-cost.md` with `SYNAPSE_FROM_AGENT=1` examples
- [ ] T042 Run quickstart smoke from `specs/004-cost-observability/quickstart.md` and save transcript in `specs/004-cost-observability/quickstart-results.md`
- [ ] T043 Run ruff on changed files with `uvx ruff check src/synapse_memory/cost src/synapse_memory/llm/claude.py src/synapse_memory/llm/apfel.py src/synapse_memory/cli.py tests/test_cost_events.py tests/test_cost_summary.py tests/test_cost_cli.py tests/test_llm_claude.py tests/test_apfel.py`
- [ ] T044 Run mypy strict on new modules with `python3 -m mypy --strict src/synapse_memory/cost`
- [ ] T045 Run full tests with `python3 -m pytest tests/ -W ignore::DeprecationWarning`
- [ ] T046 Run redaction golden eval and record Pass1/Pass2 F1 in `specs/004-cost-observability/redaction-eval-results.md`
- [ ] T047 Review `git diff --check` and remove unrelated changes before commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1; blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2; MVP.
- **Phase 4 US2**: Depends on Phase 2; can run after or alongside US1, but `src/synapse_memory/cli.py` conflicts mean sequential implementation is safer.
- **Phase 5 US3**: Depends on Phase 2 and reinforces US1/US2 safety paths.
- **Phase 6 Polish**: Depends on selected user stories.

### MVP Scope

Complete Phase 1, Phase 2, and Phase 3. This delivers automatic cost event logging without waiting for summary UI polish.

### Parallel Opportunities

- T001-T003 can run in parallel.
- T004/T005 and T008 can run in parallel before T006/T007/T009.
- US1 test tasks T011-T015 can run in parallel.
- US2 test tasks T022-T025 can run in parallel.
- US3 test tasks T031-T034 can run in parallel.
- Documentation tasks T040-T041 can run in parallel after CLI shape stabilizes.

## Parallel Examples

```bash
# US1 tests can be drafted together:
Task: "Write failing Claude success cost logging tests in tests/test_llm_claude.py"
Task: "Write failing apfel success cost logging tests in tests/test_apfel.py"
Task: "Write failing command context tests in tests/test_cost_events.py"
```

```bash
# US2 tests can be drafted together:
Task: "Write failing summary date filtering tests in tests/test_cost_summary.py"
Task: "Write failing JSON output tests in tests/test_cost_cli.py"
```

## Implementation Strategy

1. Deliver MVP first: CostEvent storage + Claude/apfel wrapper logging.
2. Add `cost summary` once rows are reliable and private.
3. Harden corrupt-tail recovery and logging failure isolation.
4. Run full quality gates and redaction eval before PR.
