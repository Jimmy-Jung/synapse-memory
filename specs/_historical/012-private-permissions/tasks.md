---
description: "Task list for 012-private-permissions feature implementation"
---

# Tasks: Private 폴더 + 외부 AI 차단 + /sm:redact

**Input**: Design documents from `/specs/012-private-permissions/`
**Prerequisites**: plan.md (✅), spec.md (✅)

**Tests**: 포함됨 (Constitution III. Test-First Discipline)
**Organization**: US 단위 그룹화. US1 (redact CLI) P1, US2 (doctor + docs) P1, US3 (Codex 가이드) P2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일·의존성 없음 → 병렬 가능
- **[Story]**: US1 (redact file CLI) / US2 (doctor + docs) / US3 (Codex 가이드)

**plan.md 정정 사항 (구현 중 반영)**:
- apfel helper: `detect_environment()` from `synapse_memory.llm.apfel` (throws `ApfelUnavailableError` if 미설치)
- doctor 명명: `diagnose_*` 함수 + `DiagnosticResult` + `DiagnosticStatus` enum (CheckResult 아님)

---

## Phase 1: Setup

- [ ] T001 사양 정합성 확인: `cli.py:p_redact = sub.add_parser("redact", ...)` 위치(line ~2215)에 `file` 액션 추가 지점 확인. `redact_sub`에 backfill과 동일 레벨로 file 추가
- [ ] T002 `redaction/__init__.py` 의 `redact_full` 시그니처 확인 (text, env, …)
- [ ] T003 `llm/apfel.py:detect_environment` 호출 패턴 확인 (다른 모듈이 어떻게 호출하는지)

---

## Phase 2: US1 — `redact file` CLI

### Tests (Red)

- [ ] T004 [P] [US1] `tests/test_cli_redact_file.py` 작성 (5 시나리오):
  - `test_redact_file_basic`: PII 포함 합성 markdown → stdout에 redacted, exit 0, 원본 보존
  - `test_redact_file_redactlist_masked`: redactlist 등록 단어 → placeholder로 마스킹 (monkeypatch로 redactlist 주입)
  - `test_redact_file_out_option`: `--out path` → stdout 안 쓰고 파일에 기록, exit 0
  - `test_redact_file_missing_path_exit_2`: 존재하지 않는 경로 → exit 2, stderr 메시지
  - `test_redact_file_binary_exit_2`: UTF-8 디코드 실패 (예: bytes 0xFF 0xFE) → exit 2
- [ ] T005 [US1] `pytest tests/test_cli_redact_file.py` → 5개 모두 실패 (`cmd_redact_file` 미존재)

### Implementation (Green)

- [ ] T006 [US1] `src/synapse_memory/cli.py`에 `cmd_redact_file(args)` 함수 추가:
  - 입력 검증 (exists / size ≤ 1 MB / UTF-8)
  - `detect_environment()` 호출 try/except `ApfelUnavailableError` → Pass 1 only fallback + stderr 경고
  - 성공 시 `redact_full(text, env=...)` 또는 `pass1.redact(text)`
  - `--out` 처리, stdout 처리, exit code 반환
- [ ] T007 [US1] `build_parser()`의 `redact_sub`에 `file` 액션 추가:
  - 인자: `path` (positional), `--out PATH` (optional)
  - `set_defaults(func=cmd_redact_file)`
- [ ] T008 [US1] `pytest tests/test_cli_redact_file.py` → 5개 모두 통과
- [ ] T009 [US1] 1 MB 한도·apfel fallback 추가 시나리오 (선택):
  - `test_redact_file_size_limit_exit_2`: 1 MB 초과 → exit 2
  - `test_redact_file_apfel_fallback`: `detect_environment` monkeypatch로 ApfelUnavailableError → Pass 1만 적용 + stderr 경고

**Checkpoint**: US1 단독 동작. 슬래시 매핑(T015) 전에도 CLI는 사용 가능.

---

## Phase 3: US2 — doctor 체크 + docs

### Tests (Red)

- [ ] T010 [P] [US2] `tests/test_doctor_private_check.py` 작성 (3 시나리오):
  - `test_diagnose_private_skip_when_no_folder`: vault에 Private 폴더 없음 → `DiagnosticStatus.SKIPPED`
  - `test_diagnose_private_warn_when_no_settings`: Private 폴더 있고 `.claude/settings.json` 없음 → WARN
  - `test_diagnose_private_warn_when_deny_missing`: settings.json에 일부 deny만 있음 → WARN (누락 항목 메시지)
  - `test_diagnose_private_ok_when_all_three_deny`: Read/Glob/Write 셋 다 deny → OK
- [ ] T011 [US2] `pytest tests/test_doctor_private_check.py` → 4개 실패

### Implementation (Green)

- [ ] T012 [US2] `src/synapse_memory/doctor.py`에 `diagnose_private_folder_deny(vault: Path) -> DiagnosticResult` 추가:
  - vault `90_System/Private/` 존재 체크 → 없으면 SKIPPED
  - vault `.claude/settings.json` 파싱 → 없으면 WARN
  - `permissions.deny` 배열에서 required 3개 (Read/Glob/Write) 누락 여부 → 누락 시 WARN
  - 모두 있으면 OK
- [ ] T013 [US2] `cmd_doctor` 또는 doctor의 등록 list에 신규 체크 함수 연결 (기존 패턴 따름)
- [ ] T014 [US2] `pytest tests/test_doctor_private_check.py` → 통과

### docs

- [ ] T015 [P] [US2] `docs/reference.md`에 "Private 메모 안전 전달" 섹션 추가:
  - vault `90_System/Private/` 관례 소개
  - vault `.claude/settings.json` permissions.deny 예시 (Read/Glob/Write 셋 다)
  - `synapse-memory redact file <path>` 사용법
  - `synapse-memory doctor` 자가진단 안내

### Slash command + skill

- [ ] T016 [P] [US2] `commands/redact.md` 작성 (Claude Code marketplace command):
  - `!synapse-memory redact file $ARGUMENTS` 형식
  - usage 예시 + --out 옵션 안내
- [ ] T017 [P] [US2] `skills/redact/SKILL.md` 작성 (Codex skill):
  - name: redact, description: "private 파일을 apfel로 redact해 외부 AI에 안전하게 전달"

**Checkpoint**: US2 완료. 신규 사용자가 doctor 안내 따라가면 안전한 vault 설정.

---

## Phase 4: US3 — Codex 격리 정책 가이드

- [ ] T018 [US3] `docs/reference.md`에 "Codex 격리 정책" 하위 섹션 추가:
  - Codex가 permissions.deny 동등 기능 없음을 명시
  - vault 루트 `AGENTS.md`에 진입 금지 한 줄 추가 권장
  - 또는 작업 디렉터리를 vault 루트가 아닌 sub-folder로 분리하는 패턴
- [ ] T019 [US3] (선택) 사용자 vault에 `AGENTS.md` 신규 생성 시 사용할 템플릿 sample을 `docs/templates/AGENTS-with-private.md`로 제공

**Checkpoint**: US3 docs 완료. Codex 사용자는 정책 가이드로 안전 운영.

---

## Phase 5: Polish & Release

- [ ] T020 전체 회귀: `pytest -q` 통과 (847+5+4=856 예상)
- [ ] T021 manual smoke: 실제 vault에 합성 private 파일 1개 두고 `synapse-memory redact file` 호출 → 결과 검토
- [ ] T022 manual smoke 2: `synapse-memory doctor` 호출 → Private 체크 출력 확인
- [ ] T023 `CHANGELOG.md`에 0.10.0 항목 추가
- [ ] T024 `pyproject.toml` version 0.9.0 → 0.10.0 (사용자 work style: 기능 단위 + 릴리즈)
- [ ] T025 PR 생성 (source `0.10.0/feature/012-private-permissions`, target `main`)

---

## Dependencies & Execution Order

### Phase

- Phase 1 (Setup): 즉시 시작
- Phase 2 (US1): Phase 1 후
- Phase 3 (US2): Phase 1 후 (US1과 독립, 병렬 가능)
- Phase 4 (US3): Phase 3 후 (docs 같은 파일 편집 충돌 회피)
- Phase 5: 모두 완료 후

### Parallel Opportunities

- T004 ↔ T010 — 다른 test 파일, 병렬 가능
- T015 ↔ T016 ↔ T017 — docs/commands/skills 각각 다른 파일, 병렬
- Phase 2 vs Phase 3 — 다른 사람이라면 병렬, 1인은 순차

---

## Implementation Strategy

### MVP (US1 only)

1. Phase 1 + 2 — `synapse-memory redact file` 1개만 ship
2. validate 후 머지하면 사용자는 docs 없이도 CLI는 사용 가능

### Incremental Delivery (권장)

1. Phase 1 + 2 (US1) — redact CLI ~2시간
2. Phase 3 (US2) — doctor + docs ~2시간
3. Phase 4 (US3) — Codex 가이드 ~30분
4. Phase 5 — release ~30분

총 예상: 0.5~1일 작업

---

## Notes

- [P] = 다른 파일, 의존성 없음 → 병렬 가능
- 모든 Test는 Red(실패) 확인 후 Green
- 기능 단위 커밋: Phase 단위로 commit
- 커밋 전 불필요 주석 제거 (사용자 work style)
- vault `.claude/settings.json` 변경은 **사용자 책임** — 도구는 안내만, 자동 수정 X (Constitution VI Installation Consent)
