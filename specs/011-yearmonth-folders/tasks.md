---
description: "Task list for 011-yearmonth-folders feature implementation"
---

# Tasks: MemoryInbox / DailyReports 년·월 폴더 구조

**Input**: Design documents from `/specs/011-yearmonth-folders/`
**Prerequisites**: plan.md (✅), spec.md (✅)

**Tests**: 포함됨 (Constitution Principle III. Test-First Discipline 준수)
**Organization**: User story 단위로 묶음. P1 두 개(US1, US2)는 같은 sprint에서 처리, P2(US3)는 회귀 검증.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일·서로 의존성 없음 → 병렬 가능
- **[Story]**: US1 (auto path 생성) / US2 (migrate-folders CLI) / US3 (dataview 호환 검증)
- 모든 task에 정확한 파일 경로 명시

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 신규 패키지 디렉터리·테스트 디렉터리 구조 확보

- [ ] T001 `src/synapse_memory/folders/` 디렉터리 생성 + 빈 `__init__.py`
- [ ] T002 `tests/__init__.py` 존재 확인 (이미 있음 → skip)
- [ ] T003 ~~tests/unit, tests/integration 분리~~ — 기존 컨벤션은 평탄 `tests/`이므로 task 삭제. 모든 신규 테스트는 `tests/test_*.py`로 직접 추가

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: US1과 US2 모두가 의존하는 공통 path helper.

**⚠️ CRITICAL**: 이 phase 완료 전엔 US1·US2 둘 다 진입 불가.

### Tests (Red, 작성 후 실패 확인)

- [ ] T004 [P] `tests/test_folders_path.py` 작성:
  - `test_year_month_path_basic`: `year_month_path(Path("/tmp/x"), date(2026, 5, 17))` → `Path("/tmp/x/2026/05")`
  - `test_year_month_path_zero_pads_month`: `date(2026, 1, 9)` → `.../2026/01` (한 자리 숫자 zero-pad)
  - `test_year_month_path_year_boundary`: `date(2026, 12, 31)` vs `date(2027, 1, 1)` → 다른 폴더
  - `test_year_month_path_does_not_create_directory`: 호출 후 `path.exists()` is False (생성은 호출자 책임)
  - `test_find_candidate_files_recursive`: tmp_path에 `2026/05/Profile-2026-05-17.md` 두면 `find_candidate_files()`가 그 파일을 반환
- [ ] T005 `pytest tests/test_folders_path.py` 실행 → ImportError로 5개 모두 실패 (Red 확인)

### Implementation (Green)

- [ ] T006 `src/synapse_memory/folders/__init__.py` 작성:
  - `year_month_path(base: Path, date: datetime.date) -> Path`
  - `find_candidate_files(base: Path, pattern: str = "Profile-*.md") -> list[Path]` (재귀 glob)
- [ ] T007 `pytest tests/test_folders_path.py` → 5개 모두 통과 (Green 확인)

**Checkpoint**: foundation 완료. US1·US2 진입 가능.

---

## Phase 3: User Story 1 - 신규 daily 자동 년/월 폴더 생성 (Priority: P1) 🎯 MVP

**Goal**: `synapse-memory daily` 실행 시 신규 파일이 `{base}/{YYYY}/{MM}/` 하위에 생성

**Independent Test**: 빈 임시 vault에서 `synapse-memory daily --quick` 1회 실행 → 정확한 경로에 파일 2개 존재

### Tests for US1 (Red)

- [ ] T008 [P] [US1] `tests/test_daily_year_month.py` 작성:
  - `test_save_profile_update_uses_year_month_path`: `save_profile_update` 호출 후 tmp vault에 `90_System/AI/MemoryInbox/2026/05/Profile-2026-05-17.md` 존재
  - `test_write_daily_report_uses_year_month_path`: `write_daily_report` 호출 후 `90_System/AI/DailyReports/2026/05/2026-05-17.md` 존재
  - `test_same_month_second_run_does_not_recreate_folder`: 같은 달 2회 호출 → 폴더 mtime 변경 없음, 두 파일 모두 존재
  - `test_month_boundary_creates_new_folder`: `date(2026, 5, 31)` 호출 후 `date(2026, 6, 1)` 호출 → `2026/05/`와 `2026/06/` 둘 다 존재
  - `test_config_override_base_folder`: config의 `memory_inbox`를 임의 string으로 변경 후 호출 → 변경된 base 아래 `{YYYY}/{MM}/` 구조 유지
- [ ] T009 [US1] `pytest tests/test_daily_year_month.py` → 5개 모두 실패 확인

### Implementation for US1 (Green)

- [ ] T010 [US1] `src/synapse_memory/profile/extract.py` `save_profile_update` 수정:
  - import `from synapse_memory.folders import year_month_path`
  - `today` 변수를 `date` 객체로 유지 (isoformat은 파일명에만)
  - `inbox = year_month_path(inbox_base, today)` 패턴 적용
  - `inbox.mkdir(parents=True, exist_ok=True)` 호출
- [ ] T011 [US1] `src/synapse_memory/daily.py` `write_daily_report` 수정: 동일 패턴
- [ ] T012 [US1] `pytest tests/test_daily_year_month.py` → 5개 모두 통과
- [ ] T013 [US1] 기존 회귀 — `pytest` 전체 실행 → 459+ 테스트 모두 그린 (변경 전 baseline과 일치)

**Checkpoint**: US1 독립 동작 검증 완료. 신규 daily 호출은 새 구조로 들어감.

---

## Phase 4: User Story 2 - 기존 flat 파일 마이그레이션 (Priority: P1)

**Goal**: `synapse-memory migrate-folders` CLI로 flat 파일을 년/월 폴더로 이동, dry-run 지원, 충돌 시 fail-closed

**Independent Test**: 임시 vault에 flat 파일 N개 두고 `migrate-folders --dry-run` → N개 리스트 출력, 파일 0건 이동. 실제 실행 후 N개 모두 정확한 경로로 이동.

### Tests for US2 (Red)

- [ ] T014 [P] [US2] `tests/test_folders_migrate.py` 작성 (시나리오 7개):
  - `test_scan_flat_files_returns_plans`: tmp 폴더에 `Profile-2026-04-23.md` + `Profile-2026-05-17.md` 두면 2개 `MigrationPlan` 반환
  - `test_scan_skips_unknown_pattern`: `Profile-draft.md` 같이 정규식 안 맞는 파일은 plan 미포함, `skipped_unknown`에 들어감
  - `test_execute_dry_run_does_not_mutate`: `execute_migration(plans, dry_run=True)` → `moved` 리스트는 채워지지만 실제 파일 이동 0
  - `test_execute_real_moves_files`: dry_run=False → 파일이 실제 dst로 이동, src는 사라짐
  - `test_execute_detects_collision`: dst 파일이 이미 존재하면 그 plan은 `conflicts`로 분류, 이동 안 함
  - `test_execute_idempotent_after_success`: 한 번 실행 후 다시 scan → plans 비어 있음
  - `test_execute_partial_failure_continues`: 일부 파일이 permission error여도 나머지는 처리, error 리스트로 보고
- [ ] T015 [US2] `pytest tests/test_folders_migrate.py` → 7개 모두 실패

### Implementation for US2 (Green)

- [ ] T016 [US2] `src/synapse_memory/folders/migrate.py` 작성:
  - `MigrationPlan`, `MigrationResult` dataclass
  - `PROFILE_PATTERN = re.compile(r"^Profile-(\d{4})-(\d{2})-(\d{2})\.md$")`
  - `DAILY_REPORT_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")`
  - `scan_flat_files(folder: Path, pattern: re.Pattern) -> tuple[list[MigrationPlan], list[Path]]` (plans, skipped)
  - `execute_migration(plans, *, dry_run=False) -> MigrationResult` — shutil.move 사용, 충돌 검사 후 fail-closed
- [ ] T017 [US2] `pytest tests/test_folders_migrate.py` → 7개 모두 통과

### CLI 추가 (Green continued)

- [ ] T018 [US2] `src/synapse_memory/cli.py`에 `migrate-folders` 서브커맨드 추가:
  - Options: `--dry-run`, `--report-unknown`, `--vault PATH`
  - MemoryInbox와 DailyReports 두 폴더 모두 처리 (`PROFILE_PATTERN`, `DAILY_REPORT_PATTERN` 각각)
  - 출력: 이동 대상 N개, 충돌 M개, skipped K개 (--report-unknown 시 list)
  - 종료 코드: 0=정상 / 1=충돌 존재 / 2=시스템 에러
- [ ] T019 [US2] `tests/test_cli_migrate_folders.py` 작성 (3 시나리오):
  - `test_cli_dry_run_zero_mutations`: tmp vault에 flat 파일 두고 CLI 호출 후 `git status` 없이 file count 비교 → 변경 없음, exit 0
  - `test_cli_real_run_moves_files`: CLI 호출 후 모든 파일이 정확한 경로로
  - `test_cli_collision_returns_exit_1`: 충돌 상황 만들고 호출 → exit code 1, stderr에 충돌 메시지
- [ ] T020 [US2] `pytest tests/test_cli_migrate_folders.py` → 통과

**Checkpoint**: US2 독립 동작 검증 완료. 기존 vault 사용자가 새 구조로 옮길 수 있음.

---

## Phase 5: User Story 3 - dataview 호환 회귀 검증 (Priority: P2)

**Goal**: 기존 dataview 쿼리가 새 구조에서도 동작

**Independent Test**: 실제 vault의 백업본에서 마이그레이션 전후 dataview 결과 일치 확인 (수동)

### Manual Verification (코드 변경 없음)

- [ ] T021 [US3] 사용자 vault 백업본 생성 (`cp -R "vault" "/tmp/vault-backup-pre-migration"`)
- [ ] T022 [US3] 마이그레이션 전 vault에서 `90_System/Home.md`와 `90_System/AI/` 인덱스 노트의 dataview 결과 캡처 (스크린샷 또는 결과 리스트 메모)
- [ ] T023 [US3] `synapse-memory migrate-folders --dry-run` 호출 → 의도된 이동 리스트 검토
- [ ] T024 [US3] 실제 `synapse-memory migrate-folders` 실행
- [ ] T025 [US3] Obsidian에서 동일 dataview 쿼리 결과 재확인 → 항목 수·내용 일치 검증
- [ ] T026 [US3] 검증 결과를 `specs/011-yearmonth-folders/verification-2026-05-XX.md`에 기록 (passed / regressions)

**Checkpoint**: 회귀 없음 확인. 안전하게 main 머지 가능.

---

## Phase 6: Polish & Release

- [ ] T027 [P] `docs/development.md` 갱신 — 신규 폴더 구조 명시
- [ ] T028 [P] `README.md` 갱신 — vault 구조 다이어그램 (있다면)
- [ ] T029 `CHANGELOG.md` 또는 release notes에 0.9.0 항목 추가:
  - "MemoryInbox / DailyReports: year/month folder structure"
  - "New: `synapse-memory migrate-folders` for one-shot migration of legacy flat files"
- [ ] T030 `pyproject.toml` version `0.8.5 → 0.9.0` (사용자 work style: 기능 단위 커밋 + 릴리즈)
- [ ] T031 전체 회귀: `pytest -q` 통과 + manual smoke (실제 vault에서 daily 1회)
- [ ] T032 PR 생성 (대상 브랜치 `main`, source `0.9.0/feature/011-yearmonth-folders`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 의존성 없음, 즉시 시작
- **Phase 2 (Foundational)**: Phase 1 후. US1·US2 모두 차단
- **Phase 3 (US1)**: Phase 2 후. US2와 독립
- **Phase 4 (US2)**: Phase 2 후. US1과 독립 (병렬 가능)
- **Phase 5 (US3)**: Phase 3 + Phase 4 둘 다 완료 후 (실제 마이그레이션 실행이 필요)
- **Phase 6 (Polish)**: 모두 완료 후

### Within Each User Story

- 모든 test (Red) → 실패 확인 → implementation (Green) 순서 엄수
- 같은 파일에 손대는 task는 순차 (T010 → T011은 다른 파일이라 [P] 가능)

### Parallel Opportunities

- Phase 1: T001, T002, T003 모두 독립 (병렬 가능)
- Phase 2: T004는 단일 파일, 병렬 의미 없음
- Phase 3 vs Phase 4: 독립 (다른 사용자 작업 가능, 1인은 순차)
- T010과 T011: 다른 파일 → [P]
- T027과 T028: 다른 파일 → [P]

---

## Implementation Strategy

### MVP (US1 only)

1. Phase 1 + 2 완료
2. Phase 3 (US1) 완료 → 신규 daily는 정돈된 구조
3. **STOP and VALIDATE**: 실제 vault에서 `synapse-memory daily --quick` 1회 실행 → 새 구조 확인
4. (선택) US1만 머지하고 US2 별도 PR — 위험 더 작게

### Incremental Delivery (이번 sprint 권장 흐름)

1. Phase 1 + 2 (~1시간)
2. Phase 3 (US1, ~2시간)
3. Phase 4 (US2, ~3시간)
4. Phase 5 (US3, manual ~30분)
5. Phase 6 (polish + release, ~30분)

총 예상: 1일 작업 (느슨하게 잡으면 1.5일)

---

## Notes

- [P] = 다른 파일, 의존성 없음 → 병렬 가능
- [Story] 라벨로 어떤 user story에 속하는지 추적
- Test는 반드시 Red(실패) 확인 후 Green
- 기능 단위 커밋: Phase 단위 또는 task 묶음 단위로 commit (사용자 work style)
- 커밋 전 불필요 주석 제거 (사용자 work style)
- 같은 파일 동시 작업 금지 (`profile/extract.py`, `daily.py`는 US1 내에서 순차)
