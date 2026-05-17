---
description: "Task list for 014-apply-profile feature implementation"
---

# Tasks: /sm:apply-profile + /sm:daily 자동 연결

**Input**: Design from `/specs/014-apply-profile/`

## Phase 1: CLI list-pending-profiles (TDD)

- [ ] T001 [P] `tests/test_cli_list_pending_profiles.py` 작성 (3 시나리오):
  - `test_list_pending_recursive_scan`: `{YYYY}/{MM}/` 하위 + flat 파일 모두 탐지
  - `test_list_pending_excludes_applied`: status=applied 파일은 제외
  - `test_list_pending_json_output`: `--json` 출력 형식
- [ ] T002 Red 확인
- [ ] T003 `cli.py`에 `cmd_list_pending_profiles` 추가 (folders.find_candidate_files 재사용 + frontmatter status 파싱)
- [ ] T004 서브파서 등록 (`list-pending-profiles`, `--vault`, `--json`)
- [ ] T005 Green 확인

## Phase 2: Slash command + skill + docs

- [ ] T006 [P] `commands/apply-profile.md` — 핵심 prompt (list-pending JSON 호출 → 파싱 → 4개씩 AskUserQuestion → 승인분 Edit → status: applied)
- [ ] T007 [P] `skills/apply-profile/SKILL.md` — Codex skill 정의
- [ ] T008 `commands/daily.md` 수정 — 마지막에 apply 흐름 안내 추가 (사용자 yes 후 진입)
- [ ] T009 [P] `docs/reference.md` — "Profile 후보 GUI 승인" 섹션 추가

## Phase 3: Release

- [ ] T010 전체 회귀: `pytest -q` 통과
- [ ] T011 manual smoke: 실제 vault MemoryInbox에서 `synapse-memory list-pending-profiles` 실행 → 출력 확인
- [ ] T012 `CHANGELOG.md`에 0.12.0 항목 추가
- [ ] T013 `pyproject.toml` version 0.11.0 → 0.12.0
- [ ] T014 PR 생성
