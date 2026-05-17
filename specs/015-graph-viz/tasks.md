---
description: "Task list for 015-graph-viz feature implementation (P1+P2 only)"
---

# Tasks: Obsidian Graph 시각화 — node 태그 + MOC + doctor

**Input**: Design from `/specs/015-graph-viz/`. US4 (Suggested wikilink) 본 sprint 범위 밖.

## Phase 1: node 태그 (US1)

- [ ] T001 [P] `tests/test_node_tags.py` 작성 (4 시나리오)
- [ ] T002 Red 확인
- [ ] T003 `cards/auto_generate.py` 또는 동등 — generate_project_card / generate_company_card frontmatter `tags`에 `node/card` 추가
- [ ] T004 `profile/extract.py:save_profile_update` frontmatter `tags: [node/profile-update]` 추가
- [ ] T005 `daily.py:render_daily_report` frontmatter `tags: [node/daily-report]` 추가
- [ ] T006 Green 확인 (4 tests) + 회귀

## Phase 2: doctor Dataview 체크 (US3)

- [ ] T007 [P] `tests/test_doctor_dataview_check.py` 작성 (3 시나리오)
- [ ] T008 Red 확인
- [ ] T009 `doctor.py`에 `diagnose_dataview_plugin(vault)` 추가
- [ ] T010 `cli.py:cmd_doctor`에 진단 호출 등록
- [ ] T011 Green 확인

## Phase 3: MOC generator (US2)

- [ ] T012 [P] `tests/test_moc_generator.py` 작성 (3 시나리오)
- [ ] T013 Red 확인
- [ ] T014 `src/synapse_memory/moc/__init__.py`:
  - `MOC_MARKER_START`/`MOC_MARKER_END` 상수
  - `generate_moc_body(vault) -> str` (dataview 블록 markdown)
  - `write_or_update_moc(vault) -> Path` (marker 패턴, 사용자 영역 보존)
- [ ] T015 `cli.py`에 `cmd_moc` + `moc` 서브파서 등록
- [ ] T016 Green + 회귀

## Phase 4: docs + slash/skill

- [ ] T017 [P] `commands/moc.md`
- [ ] T018 [P] `skills/moc/SKILL.md`
- [ ] T019 [P] `docs/reference.md` "Obsidian Graph 시각화" 섹션

## Phase 5: Release

- [ ] T020 전체 회귀: `pytest -q` 통과 (879 + ≥10 = 889+)
- [ ] T021 manual smoke: `synapse-memory moc` 실제 vault 호출
- [ ] T022 manual smoke: Obsidian Graph node/* 색상 분리 확인
- [ ] T023 `CHANGELOG.md`에 0.13.0
- [ ] T024 `pyproject.toml` 0.12.0 → 0.13.0
- [ ] T025 PR 생성
