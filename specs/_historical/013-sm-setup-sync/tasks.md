---
description: "Task list for 013-sm-setup-sync feature implementation"
---

# Tasks: /sm:setup + /sm:sync — cross-project Profile marker

**Input**: Design documents from `/specs/013-sm-setup-sync/`
**Prerequisites**: plan.md (✅), spec.md (✅)

**Tests**: 포함됨 (Constitution III. Test-First Discipline)
**Organization**: 모듈 단위 (marker / registry / summary) → CLI 통합 → docs.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일·의존성 없음 → 병렬 가능
- **[Story]**: US1 (setup) / US2 (sync) / US3 (cross-AI 호환)

---

## Phase 1: Setup

- [ ] T001 `src/synapse_memory/projects/` 디렉터리 + 빈 `__init__.py`
- [ ] T002 PyYAML 의존성 확인 (pyproject.toml에 이미 있음)

---

## Phase 2: marker module

### Tests (Red)

- [ ] T003 [P] `tests/test_projects_marker.py` 작성 (6 시나리오):
  - `test_inject_into_new_file`
  - `test_append_to_existing_file`
  - `test_replace_existing_marker_idempotent`
  - `test_byte_level_idempotent`
  - `test_unclosed_marker_raises`
  - `test_extract_block_returns_body`
- [ ] T004 `pytest tests/test_projects_marker.py` → 6 실패

### Implementation (Green)

- [ ] T005 `src/synapse_memory/projects/marker.py`:
  - `MARKER_START`, `MARKER_END` 상수
  - `MarkerParseError(ValueError)`
  - `extract_block(file: Path) -> str | None`
  - `inject_or_replace(file: Path, body: str) -> tuple[bool, str | None]`
- [ ] T006 `pytest tests/test_projects_marker.py` → 6 통과

---

## Phase 3: registry module

### Tests (Red)

- [ ] T007 [P] `tests/test_projects_registry.py` (4):
  - `test_load_empty_when_no_file`
  - `test_save_and_load_roundtrip`
  - `test_upsert_inserts_new_and_updates_existing`
  - `test_mark_stale_updates_state`
- [ ] T008 `pytest tests/test_projects_registry.py` → 4 실패

### Implementation (Green)

- [ ] T009 `src/synapse_memory/projects/registry.py`:
  - `ProjectEntry` dataclass
  - `load_registry`, `save_registry` (atomic write: tmp + rename)
  - `upsert_entry`, `mark_stale`
- [ ] T010 `pytest tests/test_projects_registry.py` → 통과

---

## Phase 4: summary module

### Tests (Red)

- [ ] T011 [P] `tests/test_projects_summary.py` (3):
  - `test_generate_marker_body_basic`
  - `test_fact_top_n_limits_output`
  - `test_pattern_top_m_limits_output`
- [ ] T012 `pytest tests/test_projects_summary.py` → 3 실패

### Implementation (Green)

- [ ] T013 `src/synapse_memory/projects/summary.py`:
  - `generate_marker_body(profile_path, patterns_path, *, fact_top_n=5, pattern_top_m=4) -> str`
  - Profile/Patterns의 `- ` bullet 라인 상위 N/M 추출
- [ ] T014 `pytest tests/test_projects_summary.py` → 통과

---

## Phase 5: CLI 통합 (setup + sync)

### Tests (Red)

- [ ] T015 [P] `tests/test_cli_setup_sync.py` (5):
  - `test_setup_target_both_creates_files`
  - `test_setup_idempotent_byte_level`
  - `test_setup_dry_run_no_mutation`
  - `test_sync_updates_all_registered`
  - `test_sync_marks_stale_when_project_missing`
- [ ] T016 `pytest tests/test_cli_setup_sync.py` → 5 실패

### Implementation (Green)

- [ ] T017 `src/synapse_memory/cli.py`에 `cmd_setup`, `cmd_sync` 추가
- [ ] T018 `build_parser()`에 `setup` / `sync` 서브커맨드 등록
- [ ] T019 `pytest tests/test_cli_setup_sync.py` → 통과

---

## Phase 6: docs + slash/skill

- [ ] T020 [P] `docs/reference.md`에 "다른 프로젝트에서 sm 컨텍스트 활용" 섹션 추가
- [ ] T021 [P] `commands/setup.md`
- [ ] T022 [P] `commands/sync.md`
- [ ] T023 [P] `skills/setup/SKILL.md`
- [ ] T024 [P] `skills/sync/SKILL.md`

---

## Phase 7: Release

- [ ] T025 전체 회귀: `pytest -q` 통과 (858 + ≥18 = 876+)
- [ ] T026 manual smoke: 임시 디렉터리에서 setup → AGENTS.md/CLAUDE.md 생성 + projects.yaml 확인
- [ ] T027 manual smoke: vault Profile 수정 후 sync → marker 갱신 확인
- [ ] T028 `CHANGELOG.md`에 0.11.0 항목 추가
- [ ] T029 `pyproject.toml` version 0.10.0 → 0.11.0
- [ ] T030 PR 생성

---

## Dependencies & Execution Order

- Phase 1: 즉시 시작
- Phase 2-4: 모듈 독립, 1인은 순차
- Phase 5: Phase 2-4 모두 완료 후
- Phase 6: Phase 5 후
- Phase 7: 모두 완료 후

### Parallel Opportunities

- T003 / T007 / T011: 다른 test 파일 — 병렬
- T020-T024: 다른 docs/skill/command 파일 — 병렬

---

## Implementation Strategy

총 예상: 0.5~1일.

Phase 1+2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 순.

각 Phase 완료 시 commit.

---

## Notes

- 모든 Test는 Red 확인 후 Green
- 기능 단위 커밋
- registry는 atomic write (tmp+rename) — 동시 호출 안전
- 사용자 수동 편집 marker는 backup 후 교체 — `~/.synapse/sync-backups/`
- auto-trigger 없음 (사용자 명시 호출만)
