# Tasks: Feedback Loop

**Input**: Design documents from `/specs/003-feedback-loop/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required by project constitution. Each behavior task has a RED test task before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create feature scaffolding without behavior.

- [X] T001 [P] Create feedback package exports in `src/synapse_memory/feedback/__init__.py`
- [X] T002 [P] Create empty test modules `tests/test_feedback_events.py`, `tests/test_feedback_targets.py`, `tests/test_feedback_apply.py`, `tests/test_feedback_cli.py`, `tests/test_last_response.py`, `tests/test_profile_patterns.py`
- [X] T003 [P] Create slash command doc shell in `commands/synapse-feedback.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data and storage primitives that all user stories depend on.

- [X] T004 [P] Write failing FeedbackEvent id/action/weight/reason validation tests in `tests/test_feedback_events.py`
- [X] T005 [P] Write failing append-only/recovery/permission tests in `tests/test_feedback_events.py`
- [X] T006 Implement FeedbackEvent dataclass, id generation, reason masking, validation in `src/synapse_memory/feedback/events.py`
- [X] T007 Implement append-only JSONL writer and corruption recovery in `src/synapse_memory/feedback/events.py`
- [X] T008 [P] Write failing LastAnswerReference read/write/no-answer-text tests in `tests/test_last_response.py`
- [X] T009 Implement LastAnswerReference dataclasses and private file read/write in `src/synapse_memory/storage/last_response.py`
- [X] T010 Run foundational tests with `python3 -m pytest tests/test_feedback_events.py tests/test_last_response.py -q`

**Checkpoint**: Feedback events and last-answer storage are ready for user stories.

---

## Phase 3: User Story 1 - 직전 답변에 피드백 남기기 (Priority: P1) MVP

**Goal**: Record accept/reject/weight feedback for the most recent AI answer.

**Independent Test**: After an answer-producing endpoint succeeds, `synapse-memory feedback last --reject "<reason>"` records one event and prints the target/effect summary.

### Tests for User Story 1

- [X] T011 [P] [US1] Write failing target resolution tests for `feedback last` in `tests/test_feedback_targets.py`
- [X] T012 [P] [US1] Write failing CLI tests for `feedback last --accept/--reject/--weight` in `tests/test_feedback_cli.py`
- [X] T013 [P] [US1] Write failing no-context/no-partial-write tests for `feedback last` in `tests/test_feedback_cli.py`
- [X] T014 [P] [US1] Write failing endpoint last-response tests for `ask` in `tests/test_endpoints_ask.py`
- [X] T015 [P] [US1] Write failing endpoint last-response tests for `what_did_i_think` and `decide` in `tests/test_endpoints_me_extra.py`

### Implementation for User Story 1

- [X] T016 [US1] Implement `resolve_last_answer_targets` in `src/synapse_memory/feedback/targets.py`
- [X] T017 [US1] Add `feedback last` argparse wiring and handler in `src/synapse_memory/cli.py`
- [X] T018 [US1] Persist last-answer references after successful `ask` answers in `src/synapse_memory/endpoints/ask.py`
- [X] T019 [US1] Persist last-answer references after successful `what_did_i_think` and `decide` answers in `src/synapse_memory/endpoints/me.py`
- [X] T020 [US1] Ensure `feedback last` writes no event when context is missing or invalid in `src/synapse_memory/cli.py`
- [X] T021 [US1] Run US1 tests with `python3 -m pytest tests/test_feedback_targets.py tests/test_feedback_cli.py tests/test_endpoints_ask.py tests/test_endpoints_me_extra.py -q`

**Checkpoint**: User Story 1 is independently usable as the MVP.

---

## Phase 4: User Story 2 - 특정 카드나 패턴에 직접 가중치 조정하기 (Priority: P2)

**Goal**: Record feedback directly against a known Card or DecisionPattern.

**Independent Test**: `feedback card <id> --reject "<reason>"` and `feedback pattern <id> --weight -0.3` validate targets and append target-specific events.

### Tests for User Story 2

- [X] T022 [P] [US2] Write failing card target validation tests in `tests/test_feedback_targets.py`
- [X] T023 [P] [US2] Write failing DecisionPatterns parsing/id tests in `tests/test_profile_patterns.py`
- [X] T024 [P] [US2] Write failing CLI tests for `feedback card` and validation errors in `tests/test_feedback_cli.py`
- [X] T025 [P] [US2] Write failing CLI tests for `feedback pattern` and validation errors in `tests/test_feedback_cli.py`

### Implementation for User Story 2

- [X] T026 [US2] Implement card target lookup across ProjectCard and CompanyCard in `src/synapse_memory/feedback/targets.py`
- [X] T027 [US2] Implement DecisionPatterns.md parser and stable pattern id lookup in `src/synapse_memory/profile/patterns.py`
- [X] T028 [US2] Implement pattern target lookup in `src/synapse_memory/feedback/targets.py`
- [X] T029 [US2] Add `feedback card` and `feedback pattern` argparse wiring in `src/synapse_memory/cli.py`
- [X] T030 [US2] Run US2 tests with `python3 -m pytest tests/test_feedback_targets.py tests/test_profile_patterns.py tests/test_feedback_cli.py -q`

**Checkpoint**: User Stories 1 and 2 work independently.

---

## Phase 5: User Story 3 - 다음 검색 품질에 피드백 반영하기 (Priority: P3)

**Goal**: Convert accumulated card feedback into bounded ranking metadata and query score adjustment.

**Independent Test**: A card with one reject event receives a lower `feedback_score` on the next index/search cycle; a card with one accept event receives a higher score.

### Tests for User Story 3

- [X] T031 [P] [US3] Write failing aggregate score clamp/order tests in `tests/test_feedback_apply.py`
- [X] T032 [P] [US3] Write failing indexer metadata tests for `feedback_score` in `tests/test_rag_indexer.py`
- [X] T033 [P] [US3] Write failing vector query reordering tests using `feedback_score` in `tests/test_rag_vector_store.py`
- [X] T034 [P] [US3] Write failing CLI/search smoke test for visible `feedback_score` in `tests/test_feedback_cli.py`

### Implementation for User Story 3

- [X] T035 [US3] Implement FeedbackAggregate and card score calculation in `src/synapse_memory/feedback/apply.py`
- [X] T036 [US3] Add `feedback_score` metadata during card indexing in `src/synapse_memory/rag/indexer.py`
- [X] T037 [US3] Apply feedback score to returned distances or ordering in `src/synapse_memory/rag/vector_store.py`
- [X] T038 [US3] Print feedback score in `rag search --show-snippet` or equivalent debug output in `src/synapse_memory/cli.py`
- [X] T039 [US3] Run US3 tests with `python3 -m pytest tests/test_feedback_apply.py tests/test_rag_indexer.py tests/test_rag_vector_store.py tests/test_feedback_cli.py -q`

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Documentation, Quality Gates, and Release Prep

**Purpose**: User-facing docs, compatibility command, and merge gates.

- [X] T040 [P] Document `feedback` commands and examples in `docs/commands.md`
- [X] T041 [P] Complete `commands/synapse-feedback.md` with `SYNAPSE_FROM_AGENT=1` examples
- [ ] T042 Run quickstart smoke from `specs/003-feedback-loop/quickstart.md` and save transcript in `specs/003-feedback-loop/quickstart-results.md`
- [X] T043 Run ruff on changed files with `uvx ruff check src/synapse_memory/feedback src/synapse_memory/storage/last_response.py src/synapse_memory/profile/patterns.py src/synapse_memory/cli.py tests/test_feedback_events.py tests/test_feedback_targets.py tests/test_feedback_apply.py tests/test_feedback_cli.py tests/test_last_response.py tests/test_profile_patterns.py`
- [X] T044 Run mypy strict on new modules with `python3 -m mypy --strict src/synapse_memory/feedback src/synapse_memory/storage/last_response.py src/synapse_memory/profile/patterns.py`
- [X] T045 Run full tests with `python3 -m pytest tests/ -W ignore::DeprecationWarning`
- [X] T046 Run redaction golden eval and record Pass1/Pass2 F1 in `specs/003-feedback-loop/redaction-eval-results.md`
- [X] T047 Review `git diff --check` and remove unrelated changes before commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1; blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2; MVP.
- **Phase 4 US2**: Depends on Phase 2; can run after or alongside US1, but CLI file conflicts mean sequential implementation is safer.
- **Phase 5 US3**: Depends on Phase 2 and benefits from US1/US2 event generation, but aggregate tests can start earlier.
- **Phase 6 Polish**: Depends on selected user stories.

### MVP Scope

Complete Phase 1, Phase 2, and Phase 3. This delivers `feedback last` end-to-end without waiting for direct card/pattern commands or ranking application.

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
Task: "Write failing target resolution tests in tests/test_feedback_targets.py"
Task: "Write failing CLI tests in tests/test_feedback_cli.py"
Task: "Write failing endpoint last-response tests in tests/test_endpoints_ask.py"
Task: "Write failing endpoint last-response tests in tests/test_endpoints_me_extra.py"
```

```bash
# US3 test design can run before implementation:
Task: "Write failing aggregate score clamp/order tests in tests/test_feedback_apply.py"
Task: "Write failing indexer metadata tests in tests/test_rag_indexer.py"
Task: "Write failing vector query reordering tests in tests/test_rag_vector_store.py"
```

## Implementation Strategy

1. Deliver MVP first: event storage + last-response tracking + `feedback last`.
2. Add direct card/pattern feedback after target validation is reliable.
3. Add aggregate score application once enough events can be generated and tested.
4. Run full quality gates and redaction eval before PR.
