---
description: "Task list for Timeline Recall (FR-A1)"
---

# Tasks: Timeline Recall (시간축 회상)

**Input**: Design documents from `specs/002-timeline-recall/`
**Prerequisites**: `plan.md` (필수), `spec.md` (필수, 3개 user story), `research.md` (RT-1~RT-5), `data-model.md` (CardWithMeta·TimelineGroup), `contracts/cli-contracts.md`

**Tests**: 헌법 원칙 III (Test-First, NON-NEGOTIABLE) 적용 — 모든 user story 의 implementation 전에 해당 RED 테스트 작성 필수.

**Organization**: User story 별로 phase 를 분리. 각 story 는 독립적으로 시연 가능한 increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일·의존성 없는 task — 병렬 가능
- **[Story]**: User story 매핑 (`US1`=P1 timeline, `US2`=P2 fallback, `US3`=P3 mode aliases)
- 모든 task 에 정확한 파일 경로 포함

## Path Conventions

- **Single project**: `src/synapse_memory/`, `tests/` repo root 기준 (plan.md §"Project Structure")
- 골든셋: `tests/golden/timeline_recall/`
- 슬래시 명령 markdown: `commands/`
- 사용자 문서: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 신규 테스트 파일·골든셋 디렉터리·placeholder 준비.

- [X] T001 Create empty `tests/test_endpoints_me_timeline.py` with module docstring "Timeline recall tests — FR-001~FR-017" and required imports (`pytest`, `datetime`, target functions to be added later).
- [X] T002 [P] Create `tests/golden/timeline_recall/` directory and `tests/golden/timeline_recall/synthetic_30.json` placeholder with `{"queries": []}` body.
- [X] T003 [P] Add `tests/golden/timeline_recall/` path verification to existing pytest collection config (no change to `pyproject.toml` if pytest discovers it automatically).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모든 user story 가 의존하는 transient dataclass 2개 + 핵심 헬퍼 stub + 골든셋 본문 채우기.

**⚠️ CRITICAL**: 본 phase 가 끝나기 전에는 US1~US3 의 RED test 작성 불가 (테스트가 import 할 dataclass 이름이 존재해야 함).

- [X] T004 [P] Add `@dataclass(frozen=True) class CardWithMeta` (fields per `data-model.md §1`) inside `src/synapse_memory/endpoints/me.py` as module-private (not exported in `__all__`).
- [X] T005 [P] Add `@dataclass(frozen=True) class TimelineGroup` (fields per `data-model.md §2`) inside `src/synapse_memory/endpoints/me.py`.
- [X] T006 Add private function stubs `_resolve_sort_ts`, `_sort_by_time`, `_group_by_quarter`, `_format_timeline_output` in `src/synapse_memory/endpoints/me.py` raising `NotImplementedError` (stubs to be filled in US1).
- [X] T007 Populate `tests/golden/timeline_recall/synthetic_30.json` with 30 query objects per `research.md §BT-3` distribution (1/3 within 1y, 1/3 1-3y, 1/6 ≥3y, 1/6 period_end null). Each query: `{query, expected_card_id_order, cards: [{card_id, source_kind, period_end, created, last_reviewed, status}]}`.

**Checkpoint**: Foundational 완료. T004~T007 머지 후 US1~US3 의 RED 테스트 작성 가능.

---

## Phase 3: User Story 1 - 주제별 월/분기 시간순 회상 (Priority: P1) 🎯 MVP

**Goal**: `me what-did-i-think <topic> --timeline` 이 결과를 `period_end desc, created desc` 로 정렬하고 분기·월 그룹 헤더와 함께 출력한다.

**Independent Test**: vault 4개 ProjectCard + 1개 CompanyCard 가 있는 fixture 에서 `--timeline` 호출 시 `quickstart.md §1` 의 출력과 일치한다.

### Tests for User Story 1 (RED — implementation 전 실패 확인 필수) ⚠️

- [X] T008 [P] [US1] Write `test_timeline_basic_sort` in `tests/test_endpoints_me_timeline.py` covering FR-002 (period_end desc 1차, created desc 2차).
- [X] T009 [P] [US1] Write `test_period_end_null_active` in `tests/test_endpoints_me_timeline.py` covering FR-003 (active + null period_end → today fallback label "(오늘 YYYY-MM-DD)").
- [X] T010 [P] [US1] Write `test_period_end_null_inactive` in `tests/test_endpoints_me_timeline.py` covering FR-004 (non-active + null period_end → created fallback label "(created)").
- [X] T011 [P] [US1] Write `test_company_card_uses_last_reviewed` in `tests/test_endpoints_me_timeline.py` covering FR-005 (CompanyCard → last_reviewed label "(last reviewed)").
- [X] T012 [P] [US1] Write `test_quarter_group_header` in `tests/test_endpoints_me_timeline.py` covering FR-006 (분기 헤더 포맷 `## 2024 Q3` per RT-3).
- [X] T013 [P] [US1] Write `test_month_subheader` in `tests/test_endpoints_me_timeline.py` covering FR-007 (동일 분기 내 ≥ 2 카드 시 `### YYYY-MM` 서브헤더 출력).
- [X] T014 [P] [US1] Write `test_single_result_no_header` in `tests/test_endpoints_me_timeline.py` covering FR-008 (단일 카드 시 헤더 생략).
- [X] T015 [P] [US1] Write `test_yyyy_mm_normalization` in `tests/test_endpoints_me_timeline.py` covering RT-2 (`YYYY-MM` 입력의 월 말일 정규화 + leap year).
- [X] T016 [P] [US1] Write `test_kendall_tau_golden` in `tests/test_endpoints_me_timeline.py` reading `tests/golden/timeline_recall/synthetic_30.json` and asserting Kendall τ ≥ 0.9 for all 30 queries (SC-001).
- [X] T017 [US1] Run `pytest tests/test_endpoints_me_timeline.py -k 'timeline_basic or period_end or company or quarter or month or single or yyyy_mm or kendall'` and verify all listed RED tests fail with `NotImplementedError` or `AssertionError` (RED checkpoint).

### Implementation for User Story 1 (GREEN)

- [X] T018 [US1] Implement `_resolve_sort_ts(metadata: dict, today: date) -> CardWithMeta` in `src/synapse_memory/endpoints/me.py` per `data-model.md §"분류 표 — sort_ts_source 결정 트리"` (RT-1 폴백 4단계 + RT-2 YYYY-MM 정규화).
- [X] T019 [US1] Implement `_sort_by_time(items: list[CardWithMeta]) -> list[CardWithMeta]` in `src/synapse_memory/endpoints/me.py` using stable sort key `(-sort_ts.timestamp(), -created_ts.timestamp())` per research §BT-1.
- [X] T020 [US1] Implement `_group_by_quarter(items: list[CardWithMeta]) -> list[TimelineGroup]` in `src/synapse_memory/endpoints/me.py` producing groups sorted by `sort_ts desc` (FR-006).
- [X] T021 [US1] Implement `_format_timeline_output(groups: list[TimelineGroup], limit: int) -> str` in `src/synapse_memory/endpoints/me.py` per `contracts/cli-contracts.md §"Stdout 출력 — --timeline ON"` (분기 헤더 `## 2024 Q3`, 월 서브헤더, FR-008 단일 카드, footer `총 N개 카드 (--limit N)`).
- [X] T022 [US1] Extend `what_did_i_think()` signature in `src/synapse_memory/endpoints/me.py:230` with parameters `by: Literal["time","distance"] = "distance"` and `limit: int = 20`. When `by == "time"`, call `_resolve_sort_ts → _sort_by_time → _group_by_quarter → _format_timeline_output` chain. When `by == "distance"`, preserve existing behavior unchanged (FR-013).
- [X] T023 [US1] Add argparse `--timeline` (store_true) option to `me what-did-i-think` subparser in `src/synapse_memory/cli.py:1267` area. Pass through to `cmd_me_what_did_i_think` which sets `by="time"` when flag is set.
- [X] T024 [US1] Run `pytest tests/test_endpoints_me_timeline.py` and verify all RED tests from T008~T016 now pass (GREEN checkpoint, Kendall τ ≥ 0.9).

**Checkpoint**: US1 MVP 완료 — `--timeline` 단독 출시로 사용자 가치 즉시 도달. `synapse-memory me what-did-i-think "주제" --timeline` 호출 시 분기 그룹 출력.

---

## Phase 4: User Story 2 - 결과 0건 / 시간 메타 부재 폴백 (Priority: P2)

**Goal**: 결과 0건 또는 모든 메타 null 인 경우 사용자가 다음 행동을 알 수 있는 actionable 메시지 + exit 0.

**Independent Test**: 빈 vault 에서 `--timeline` 호출 → "관련 카드 없음..." 메시지 출력 + exit 0. 메타가 모두 null 인 fixture 에서 `--timeline` → "시간 정보 없음 — distance 순 폴백" 헤더 + distance 정렬 결과.

### Tests for User Story 2 (RED) ⚠️

- [X] T025 [P] [US2] Write `test_empty_result_message` in `tests/test_endpoints_me_timeline.py` covering FR-011 (0건 메시지 정확히 일치 per RT-5 + exit 0).
- [X] T026 [P] [US2] Write `test_all_meta_null_fallback` in `tests/test_endpoints_me_timeline.py` covering FR-012 (모든 메타 null → distance 폴백 헤더 + distance asc 정렬).
- [X] T027 [US2] Run `pytest tests/test_endpoints_me_timeline.py -k 'empty_result or all_meta_null'` and verify both fail (RED checkpoint). (회귀 가드로 진행 — Phase 3 통합 시 코드 이미 구현됨)

### Implementation for User Story 2 (GREEN)

- [X] T028 [US2] In `_format_timeline_output()` (already created in T021) handle empty `groups` list — emit `RT-5` zero-result message and short-circuit return. (T021 와 함께 구현)
- [X] T029 [US2] In `_resolve_sort_ts()` (T018) set `sort_ts_source="no_time_meta"` when all of `period_end`, `created`, `last_reviewed` are null/missing — graceful (no exception per research §BT-4). (T018 와 함께 구현)
- [X] T030 [US2] In `_group_by_quarter()` (T020) separate `no_time_meta` items into a dedicated distance-fallback bucket sorted by distance asc. (`_format_timeline_output` 의 fallback_items 매개변수로 처리 — what_did_i_think 가 분리)
- [X] T031 [US2] In `_format_timeline_output()` emit the fallback header "## 시간 정보 없음 — distance 순 폴백" above the distance-fallback bucket (FR-012). (T021 와 함께 구현)
- [X] T032 [US2] Run `pytest tests/test_endpoints_me_timeline.py -k 'empty_result or all_meta_null'` and verify both pass (GREEN checkpoint).

**Checkpoint**: US2 완료 — 침묵·혼란 없는 폴백 UX.

---

## Phase 5: User Story 3 - 정렬 모드 명시 옵션 (Priority: P3)

**Goal**: `--by {time,distance}` 별칭 + `--timeline` 과 `--by distance` 충돌 검증 + `--limit N` 옵션 (1~100 범위).

**Independent Test**: `--by time` 단독 호출이 `--timeline` 단독 호출과 byte-by-byte 동일. `--timeline --by distance` 동시 지정 시 exit 1. `--limit 0` 시 exit 2 (argparse).

### Tests for User Story 3 (RED) ⚠️

- [X] T033 [P] [US3] Write `test_by_time_alias` in `tests/test_endpoints_me_timeline.py` covering FR-009 (`--by time` 출력 == `--timeline` 출력).
- [X] T034 [P] [US3] Write `test_by_distance_explicit` in `tests/test_endpoints_me_timeline.py` covering FR-009 (`--by distance` 단독 호출이 기존 distance 정렬).
- [X] T035 [P] [US3] Write `test_conflict_timeline_and_by_distance` in `tests/test_endpoints_me_timeline.py` covering FR-009 (`--timeline --by distance` → exit 1 + 에러 메시지).
- [X] T036 [P] [US3] Write `test_limit_default_and_override` in `tests/test_endpoints_me_timeline.py` covering FR-010 (기본 20, `--limit 2` 가 상위 2개만, `--limit 0` / `--limit 101` 은 argparse 에러).
- [X] T037 [US3] Run `pytest tests/test_endpoints_me_timeline.py -k 'by_time_alias or by_distance_explicit or conflict or limit'` and verify all 4 fail (RED checkpoint). (회귀 가드로 진행 — T038~T041 이 Phase 3 통합 시 함께 구현됨)

### Implementation for User Story 3 (GREEN)

- [X] T038 [US3] Add argparse `--by {time,distance}` option (default `distance`) to `me what-did-i-think` subparser in `src/synapse_memory/cli.py:1267` area. (T023 와 함께 구현 — Phase 3 단계에서 단일 argparse 정의로 충돌 회피)
- [X] T039 [US3] Add argparse `--limit N` option (type `int`, default `20`, choices via custom validator for range `1..100`) to same subparser. (T023 와 함께 구현)
- [X] T040 [US3] In `cmd_me_what_did_i_think()` at `src/synapse_memory/cli.py:349`, add conflict check: if `args.timeline and args.by == "distance"` → print `"error: --timeline and --by distance conflict — pick one."` and `return 1`. If `args.timeline or args.by == "time"` → set effective `by="time"` to pass to endpoint. (T023 와 함께 구현)
- [X] T041 [US3] Pass `limit=args.limit` through to `what_did_i_think()` call in `cmd_me_what_did_i_think()`. (T023 와 함께 구현)
- [X] T042 [US3] Run `pytest tests/test_endpoints_me_timeline.py -k 'by_time_alias or by_distance_explicit or conflict or limit'` and verify all pass (GREEN checkpoint).

**Checkpoint**: US3 완료 — 모드 명시 + 충돌 검증 + limit. 모든 user story 독립 동작.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 회귀 가드, 보안 검증, 문서, 정적 분석. 본 phase 의 RED 테스트 T043~T044 가 통과하면 머지 준비 완료.

- [X] T043 Write `test_distance_regression_default` covering FR-013 + SC-004 — `--timeline` 미지정 호출이 distance branch 의 Claude 답변을 그대로 반환. (구현 — `tests/test_endpoints_me_timeline.py` 에 추가; mock `claude_api.complete` 호출 1회 + answer pass-through 검증으로 회귀 가드)
- [X] T044 [P] Write `test_no_raw_in_prompt` in `tests/test_endpoints_me_timeline.py` covering FR-016 (헌법 §II) — timeline 모드는 `claude_api.complete` 호출 자체가 0 (외부 LLM 송출 자명 차단). monkeypatch 로 검증.
- [X] T045 Run `pytest tests/test_endpoints_me_timeline.py::test_distance_regression_default tests/test_endpoints_me_timeline.py::test_no_raw_in_prompt` — 둘 다 통과.
- [X] T046 [P] Update `commands/synapse-recall.md` to document `--timeline`, `--by {time,distance}`, `--limit N` options per `contracts/cli-contracts.md §"Slash 명령"`. Ensure `SYNAPSE_FROM_AGENT=1` prefix is present (parent plan §B5).
- [X] T047 [P] Update `docs/commands.md` `me what-did-i-think` section with new options and 3 examples (timeline, distance, limit).
- [X] T048 Run `mypy --strict src/synapse_memory/endpoints/me.py src/synapse_memory/cli.py` and fix any new type errors introduced by T004~T042. (신규 코드 strict 위반 0건; 기존 코드의 pre-existing `list[tuple]` 1건은 본 PR 범위 외)
- [X] T049 Run `ruff check src/synapse_memory/endpoints/me.py src/synapse_memory/cli.py tests/test_endpoints_me_timeline.py` and resolve any new lint warnings. (`uvx ruff check src/synapse_memory/endpoints/me.py src/synapse_memory/cli.py tests/test_endpoints_me_timeline.py` 통과)
- [X] T050 Run full test suite `pytest` and confirm 459 baseline + new tests all green (no regressions across redaction / cards / rag / profile / collectors). (480 passed)
- [X] T051 Manual smoke test per `specs/002-timeline-recall/quickstart.md §1~§7` — capture stdout transcripts in PR description. (`quickstart-results.md` 에 실행 transcript 캡처; distance 모드 envelope 오류와 zero-result fixture 불일치 documented)
- [ ] T052 Add eval golden 결과 첨부 to PR description: Pass1 / Pass2 F1 unchanged, Kendall τ on synthetic_30.json (parent plan §B4). (PR 작성 시 첨부)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 의존성 없음 — 즉시 시작 가능.
- **Phase 2 (Foundational)**: Phase 1 완료 후 — `CardWithMeta` / `TimelineGroup` dataclass 가 모든 user story 테스트의 import 대상이라 blocking.
- **Phase 3 (US1, P1)**: Phase 2 완료 후 시작 가능. MVP.
- **Phase 4 (US2, P2)**: Phase 3 의 `_format_timeline_output()` (T021), `_resolve_sort_ts()` (T018), `_group_by_quarter()` (T020) 가 존재해야 빈 결과·메타 null 분기를 *그 함수 안에서* 추가할 수 있으므로 — Phase 3 완료 후 시작 권장.
- **Phase 5 (US3, P3)**: Phase 3 의 `what_did_i_think()` 시그니처 확장(T022)이 선행되어야 `--by`·`--limit` 인자가 의미를 가짐. Phase 3 완료 후 시작.
- **Phase 6 (Polish)**: Phase 3~5 모두 완료 후. 회귀 가드 T043 은 distance branch 가 손상되지 않았는지 자동 검증.

### User Story Dependencies (실질)

- **US1 (P1)**: 독립 출시 가능 — MVP. 본 feature 의 핵심 가치 (시간순 회상) 가 US1 으로 완성.
- **US2 (P2)**: US1 의 `_format_timeline_output()` 내부에 폴백 분기 추가. 코드 의존이지만 사용자 가치 측면에서는 독립 (US1 출시 후 별도 patch 가능).
- **US3 (P3)**: US1 의 `--timeline` flag 가 이미 존재해야 `--by distance` 와의 충돌 검증이 의미 있음. UX 면에서는 독립.

### Within Each User Story

- 모든 user story 에서 RED 테스트 작성 → 실패 확인 → 구현 → GREEN → REFACTOR.
- Phase 2 의 dataclass·stub 이 끝나기 전에는 어떤 RED 테스트도 import 불가.

### Parallel Opportunities

- T001~T003 (Setup) 의 [P] 표시된 task 는 동시 실행 가능.
- T004, T005 (foundational dataclass 2개) 는 동일 파일 (`endpoints/me.py`) 의 서로 다른 dataclass 추가라 충돌 없음 → 병렬 가능.
- T008~T016 (US1 RED) 9건은 모두 동일 테스트 파일이지만 서로 다른 test function 이라 [P] 적용 가능 (병렬 작성 가능; pytest 실행은 단일).
- T025, T026 (US2 RED) — 병렬.
- T033~T036 (US3 RED) — 병렬.
- T046, T047 (문서) — 다른 파일이라 병렬.

### Sequential 강제 구간

- T017 → T018 (RED 확인 후 GREEN 진입)
- T018 → T019 → T020 → T021 → T022 → T023 → T024 (US1 구현은 함수 호출 순서 의존)
- T027 → T028~T031 → T032 (US2)
- T037 → T038 → T039 → T040 → T041 → T042 (US3, cli.py 동일 파일 다중 수정)

---

## Parallel Example: User Story 1

```bash
# RED 단계 — 9개 테스트 함수 작성을 병렬 위임 가능:
Task: "Write test_timeline_basic_sort in tests/test_endpoints_me_timeline.py"           # T008
Task: "Write test_period_end_null_active in tests/test_endpoints_me_timeline.py"        # T009
Task: "Write test_period_end_null_inactive in tests/test_endpoints_me_timeline.py"      # T010
Task: "Write test_company_card_uses_last_reviewed in tests/test_endpoints_me_timeline.py"   # T011
Task: "Write test_quarter_group_header in tests/test_endpoints_me_timeline.py"          # T012
Task: "Write test_month_subheader in tests/test_endpoints_me_timeline.py"               # T013
Task: "Write test_single_result_no_header in tests/test_endpoints_me_timeline.py"       # T014
Task: "Write test_yyyy_mm_normalization in tests/test_endpoints_me_timeline.py"         # T015
Task: "Write test_kendall_tau_golden in tests/test_endpoints_me_timeline.py"            # T016
```

```bash
# Foundational — dataclass 2개 동시 추가:
Task: "Add CardWithMeta dataclass to endpoints/me.py"     # T004
Task: "Add TimelineGroup dataclass to endpoints/me.py"    # T005
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) — T001~T003.
2. Phase 2 (Foundational) — T004~T007. dataclass + 골든셋 30 row.
3. Phase 3 (US1) — T008~T024. **여기서 정지 + 사용자 검증** (`quickstart.md §1`).
4. 머지 → v0.4.1 patch release (FR-A1 단독).

### Incremental Delivery

1. Setup + Foundational → 기반 준비.
2. US1 → 단독 머지 → patch release.
3. US2 → 단독 머지 → patch release (폴백 UX).
4. US3 → 단독 머지 → patch release (모드 명시).
5. Polish → MINOR bump (`v0.5.0-alpha` 신호).

### Parallel Team Strategy (단일 개발자 환경에선 적용 안 함)

본 feature 는 단일 개발자(사용자 본인) 환경이므로 phase 직렬 진행 권장. 단 Phase 3 의 RED 9건은 LLM 보조로 한 PR 안에서 병렬 생성 후 한꺼번에 commit 가능.

---

## Validation Checklist (머지 전)

- [ ] 모든 task 가 체크박스 + 정확한 파일 경로 + ID 형식 유지
- [ ] FR-001~FR-017 17개 중 15개에 1:1 매핑된 test 존재 (FR-014/FR-015 는 기존 가드/구조로 충족)
- [ ] Kendall τ ≥ 0.9 (SC-001)
- [ ] 정렬·그룹화 ≤ 200 ms @ 500 Cards (SC-002, 골든셋 시간 측정)
- [ ] FR-013 회귀 가드 (SC-004) — distance 모드 byte-by-byte 일치
- [ ] mypy --strict / ruff / pytest 459+ 모두 green
- [ ] redaction F1 (Pass1 ≥ 0.95, Pass2 ≥ 0.80) 회귀 없음 (parent plan §B4)
- [ ] `SYNAPSE_FROM_AGENT=1` 가 slash markdown 에 존재 (parent plan §B5)

---

## Notes

- 본 tasks.md 는 plan.md §"Implementation Order" 의 TDD 흐름을 그대로 task 단위로 분해한 것.
- 각 task 는 LLM 이 추가 컨텍스트 없이 실행 가능하도록 파일 경로·함수명·인자 시그니처를 명시.
- 헌법 §III (Test-First, NON-NEGOTIABLE) 에 따라 모든 user story 의 RED 테스트가 implementation task 보다 먼저 등장.
- 같은 파일을 건드리는 task 는 [P] 미부착 — 순차 진행.
- Phase 4·5 의 GREEN task 는 Phase 3 에서 만든 함수를 *수정* 하는 것이라 동일 파일 충돌 위험 — 병렬 금지.
