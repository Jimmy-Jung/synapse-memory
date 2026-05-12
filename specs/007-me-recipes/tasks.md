---
description: "Implementation tasks for 007-me-recipes (Me Generator Recipes)"
---

# Tasks: Me Generator Recipes

**Input**: Design documents from `specs/007-me-recipes/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli-contracts.md](./contracts/cli-contracts.md), [quickstart.md](./quickstart.md)

**Tests**: 포함 — constitution Principle III (Test-First, NON-NEGOTIABLE) 에 따라 모든 신규 모듈에 TDD 적용. 기존 `tests/test_endpoints_me*.py` 는 무수정 유지 (SC-005 회귀 가드).

**Organization**: Phase 별로 그룹화 — Setup → Foundational → User Stories (P1→P3 순) → Polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 동일 phase 안에서 다른 파일·의존성 없음 → 병렬 가능
- **[Story]**: US1~US5 (spec.md user stories)
- 모든 경로는 repo root 기준

## Path Conventions

- 소스: `src/synapse_memory/`
- 테스트: `tests/`
- 명세 산출물: `specs/007-me-recipes/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 신규 `recipes/` 서브패키지 골격 + 빌트인 디렉터리 + 테스트 fixture 디렉터리.

- [X] T001 Create directory `src/synapse_memory/recipes/` with empty `__init__.py` exposing future public API
- [X] T002 [P] Create directory `src/synapse_memory/recipes/builtin/` (empty, recipes added in phases 3-6)
- [X] T003 [P] Create test fixture directory `tests/fixtures/recipes_vault/` with placeholder `README.md` documenting fixture layout

**Checkpoint**: 디렉터리 골격 + import path 준비. 코드는 아직 없음.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `GenerationRecipe`, `RecipeRegistry`, loader, locale/domain resolver, pipeline 의 core — 모든 user story 가 의존.

**⚠️ CRITICAL**: 이 phase 가 끝나기 전에는 어떤 user story 도 시작 불가.

### Test-First (RED — 실패 확인)

- [X] T004 [P] Write failing test `tests/test_recipes_loader.py` covering frontmatter parse (valid/malformed YAML), required-field reject, unknown-field ignore, 32KB system_prompt cap, save_subpath safety
- [X] T005 [P] Write failing test `tests/test_recipes_registry.py` covering builtin scan, user-over-builtin override, missing user dir fallback, unknown-recipe suggestion (≤3 candidates), alphabetical list ordering
- [X] T006 [P] Write failing test `tests/test_recipes_locale.py` covering 4-step precedence (CLI arg → CompanyCard.resume_language → Profile.preferred_lang → default `한국어`) + locale_source label
- [X] T007 [P] Write failing test `tests/test_recipes_domain.py` covering 3-step precedence (CLI arg → Profile.domain → tag frequency threshold ≥ 0.3 → `generic`) + domain_source label
- [X] T008 [P] Write failing test `tests/test_recipes_pipeline.py` covering full construction order (inputs validate → profile → locale → RAG → domain → render → invoke → save → last_answer), profile_used flag, no-LLM dry-run path

### Implementation (GREEN)

- [X] T009 [P] Implement `GenerationRecipe`, `GenerationContext`, `GenerationResult` frozen dataclasses in `src/synapse_memory/recipes/recipe.py` per [data-model.md §1-§4](./data-model.md)
- [X] T010 Implement frontmatter parser + validator in `src/synapse_memory/recipes/loader.py` (PyYAML, 32KB UTF-8 cap, malformed-isolate-others, save_subpath safety) — depends on T009
- [X] T011 Implement `RecipeRegistry` stateless scan in `src/synapse_memory/recipes/registry.py` (builtin+user dirs, user-over-builtin, alphabetic list, RecipeNotFoundError with difflib suggestions ≤ 3) — depends on T010
- [X] T012 [P] Implement `resolve_locale()` in `src/synapse_memory/recipes/locale.py` with precedence: cli → CompanyCard.resume_language → Profile.preferred_lang frontmatter → default `한국어` — depends on T009
- [X] T013 [P] Implement `resolve_domain()` in `src/synapse_memory/recipes/domain.py` with precedence: cli → Profile.domain → top tag frequency ≥ 0.3 → `generic` — depends on T009
- [X] T014 Implement `generate(recipe_name, inputs, ...)` orchestrator in `src/synapse_memory/recipes/pipeline.py` per [data-model.md §3](./data-model.md) construction order — depends on T009-T013
- [X] T015 [P] Add `resume_language: Optional[str] = None` field to `CompanyCard` dataclass and `load_company_card` frontmatter parser in `src/synapse_memory/cards/company.py` — independent of T009-T014
- [X] T016 Expose public API in `src/synapse_memory/recipes/__init__.py`: `generate`, `RecipeRegistry`, `RecipeNotFoundError`, `GenerationRecipe`, `GenerationResult`

**Checkpoint**: foundational green. T004-T008 모두 통과해야 다음 phase 진입.

---

## Phase 3: User Story 1 — 주간 보고 자동 생성 (Priority: P1) 🎯 MVP

**Goal**: `synapse-memory me generate weekly_report --period=2026-W19` 가 fixture vault 의 ProjectCard + Profile 을 종합해 markdown 결과를 `30_Creative/Reports/` 에 저장.

**Independent Test**: fixture vault (ProjectCard 2 + Profile.md) + `weekly_report` 빌트인 만으로 end-to-end 실행 → 저장된 markdown 에 Profile 본문 인용 확인 + last_answer 갱신.

### Test-First (RED)

- [X] T017 [P] [US1] Write failing test `tests/test_recipes_generate.py::test_weekly_report_end_to_end` using `tests/fixtures/recipes_vault/` (ProjectCard 2 건 + Profile.md + mocked `ai_api.complete`) — verify saved path, profile_used=True, source_ids 비어있지 않음, last_answer 갱신
- [X] T018 [P] [US1] Write failing test `tests/test_recipes_cli.py::test_me_generate_weekly_report` invoking CLI via subprocess — verify stdout markdown + stderr observability line (`locale=… domain=… profile_used=… matched=… duration=…`) + exit code 0

### Implementation (GREEN)

- [X] T019 [P] [US1] Create builtin recipe `src/synapse_memory/recipes/builtin/weekly_report.md` (frontmatter + system prompt, ≤ 32KB) per [research.md R-2](./research.md) and [quickstart.md §3](./quickstart.md) expected output
- [X] T020 [US1] Build `tests/fixtures/recipes_vault/` content — `90_System/AI/Profile.md` with preferred_lang/domain frontmatter, `90_System/AI/DecisionPatterns.md`, 2 ProjectCard markdown files under `20_Reference/Projects/`, empty `30_Creative/Reports/`
- [X] T021 [US1] Add `me generate <recipe> [--key=value ...] [--language] [--domain] [--model] [--vault] [--today] [--dry-run]` subcommand in `src/synapse_memory/cli.py` invoking `recipes.pipeline.generate()` — depends on T014
- [X] T022 [US1] Add TTY guard + 3-second notice + `SYNAPSE_FROM_AGENT=1` bypass for `me generate` in `src/synapse_memory/cli.py` (constitution Principle IV) — depends on T021
- [X] T023 [US1] Emit single-line observability log to stderr after each successful `me generate` invocation: `[me.generate.<name>] locale=<src:value> domain=<src:value> profile_used=<bool> matched=<count> duration=<ms>` — depends on T021
- [X] T024 [US1] Implement deterministic filename rule in `pipeline.save_result()` per [research.md R-5](./research.md): `{display_name} - {primary_input} ({YYYY-MM-DD}).md` with OS-safe normalization and timestamp-suffix collision fallback — depends on T014

**Checkpoint**: US1 fully functional. `synapse-memory me generate weekly_report --period=2026-W19` 가 fixture 에서 작동.

---

## Phase 4: User Story 2 — 이력서 voice·언어·도메인 인식 (Priority: P1)

**Goal**: `me draft-resume <company_id>` 가 Profile 을 system prompt 에 주입하고 회사·Profile 의 locale/domain 시그널에 따라 출력 언어·섹션 구조를 결정.

**Independent Test**: Profile.preferred_lang=en + Profile.domain=design fixture 로 draft_resume 호출 → markdown 에 한국어 헤더 0 개 + design-domain 섹션 (Case Studies / Tools / Impact) 등장. Profile.domain=research fixture 로 호출 → "Publications/Grants/Methodology" 섹션 등장.

### Test-First (RED)

- [X] T025 [P] [US2] Write failing test `tests/test_recipes_generate.py::test_resume_locale_english` — Profile.preferred_lang=en, CompanyCard 1 + ProjectCard 1, mock LLM with prompt capture; assert prompt 에 Profile 본문 포함, locale_source="profile", locale="English"
- [X] T026 [P] [US2] Write failing test `tests/test_recipes_generate.py::test_resume_company_card_locale_wins` — CompanyCard.resume_language=en, Profile.preferred_lang=한국어; assert locale_source="company_card", locale="English"
- [X] T027 [P] [US2] Write failing test `tests/test_recipes_generate.py::test_resume_domain_research_sections` — Profile.domain=research; assert rendered system_prompt 에 "Publications", "Grants", "Methodology" 섹션 가이드 포함 + "기술 스택" 미포함
- [X] T028 [P] [US2] Write failing test `tests/test_recipes_generate.py::test_resume_domain_design_sections` — Profile.domain=design; assert 동일하게 "Case Studies", "Tools" 등장 + IT-specific 기본 한국어 표현 0 개

### Implementation (GREEN)

- [X] T029 [P] [US2] Create builtin recipe `src/synapse_memory/recipes/builtin/resume.md` with system prompt embedding [research.md R-4](./research.md) domain matrix (software/design/research/pm/generic) via `{domain}` switch, locale via `{locale}` — must be ≤ 32KB
- [X] T030 [US2] Update `draft_resume()` in `src/synapse_memory/endpoints/me.py` to wrapper calling `recipes.pipeline.generate("resume", {"company_id": ...})` — preserve external function signature + return-type fields used by existing callers (depends on T014, T029)
- [X] T031 [US2] Remove the hardcoded "한국 IT 채용 시장" `RESUME_SYSTEM` constant from `endpoints/me.py` after T030 ships; ensure `tests/test_endpoints_me_extra.py` 와 같은 기존 시그니처 회귀 테스트가 그대로 통과
- [X] T032 [US2] Add fixture variants under `tests/fixtures/recipes_vault/` — `profile_en_design/`, `profile_en_research/`, `profile_default/` 디렉터리로 분기

**Checkpoint**: US2 fully functional. Resume 가 user voice/locale/domain 을 인식.

---

## Phase 5: User Story 3 — 사용자 recipe 즉시 발견 (Priority: P2)

**Goal**: 사용자가 `vault/90_System/AI/recipes/diary.md` 를 추가하기만 하면 `me recipes list` 와 `me generate diary` 가 즉시 작동.

**Independent Test**: 빈 빌트인 외에 사용자 `diary.md` 한 장 → `RecipeRegistry().scan()` 가 `diary` 발견 + builtin `journal` 과 동명 사용자 recipe 시 user-over-builtin 동작.

### Test-First (RED)

- [ ] T033 [P] [US3] Write failing test `tests/test_recipes_registry.py::test_user_recipe_discovered_without_restart` — write file to fixture user dir mid-test, then `RecipeRegistry.scan()`, assert `diary` in `.recipes`
- [ ] T034 [P] [US3] Write failing test `tests/test_recipes_registry.py::test_user_overrides_builtin` — both `builtin/journal.md` and `user/journal.md` exist; assert `registry.get("journal").source == "user"`
- [ ] T035 [P] [US3] Write failing test `tests/test_recipes_registry.py::test_malformed_user_recipe_isolated` — 1 malformed + 2 valid user recipes; assert valid 2 개 정상 load + skipped 리스트에 malformed 1 개 + 다른 recipe 영향 없음

### Implementation (GREEN)

- [ ] T036 [US3] Extend pipeline `last_answer` metadata to record `source = "builtin"|"user"` and `override = bool` when applicable; persist via existing `AnswerCitation`/`AnswerReference` schema (FR-011) — depends on T014
- [ ] T037 [P] [US3] Create builtin recipe `src/synapse_memory/recipes/builtin/journal.md` (frontmatter + system prompt, ≤ 32KB) per [quickstart.md §4](./quickstart.md) tone, save_subpath `10_Journal/Drafts`
- [ ] T038 [P] [US3] Create builtin recipe `src/synapse_memory/recipes/builtin/brainstorm.md` (frontmatter + system prompt, ≤ 32KB) save_subpath `30_Creative/Brainstorms`
- [ ] T039 [US3] Add quickstart automation fixture script in `tests/fixtures/recipes_vault/diary.md` (the user-recipe example from quickstart §4) used by T033

**Checkpoint**: US3 fully functional. 사용자가 markdown 한 장 추가만으로 새 결과물 종류 사용 가능.

---

## Phase 6: User Story 4 — recipes list / show CLI (Priority: P2)

**Goal**: `me recipes list` 가 모든 가용 recipe (builtin + user) 를 표 형태로 출력하고, `me recipes show <name>` 이 한 recipe 의 세부 사항을 보여줌.

**Independent Test**: builtin 4 + user 1 = 5 recipe 환경에서 `me recipes list` 가 5 행 표 + `--json` flag 가 JSON envelope 출력. `me recipes show weekly_report` 가 input_schema / rag_filter / save_subpath / system_prompt 첫 20 줄 출력.

### Test-First (RED)

- [ ] T040 [P] [US4] Write failing test `tests/test_recipes_cli.py::test_me_recipes_list_default` — fixture 의 builtin 4 + user 1 → assert stdout 에 5 행 + name 알파벳 정렬 + source 컬럼 ("builtin"/"user") + required inputs 컬럼
- [ ] T041 [P] [US4] Write failing test `tests/test_recipes_cli.py::test_me_recipes_list_json_envelope` — `--json` 출력이 [cli-contracts.md §5](./contracts/cli-contracts.md) envelope shape `{ok, data, errors}` 와 일치 + each item 의 키 set 확인
- [ ] T042 [P] [US4] Write failing test `tests/test_recipes_cli.py::test_me_recipes_show_builtin` — `me recipes show weekly_report` 출력에 name/source/source_path/description/input_schema/rag_filter/save_subpath/system_prompt preview 포함
- [ ] T043 [P] [US4] Write failing test `tests/test_recipes_cli.py::test_me_recipes_show_unknown_suggests` — `me recipes show foo` → exit code 2 + stderr 에 가까운 이름 ≤ 3 개 제안

### Implementation (GREEN)

- [ ] T044 [US4] Add `me recipes list [--source] [--vault] [--verbose] [--json]` subcommand in `src/synapse_memory/cli.py` — depends on T011
- [ ] T045 [US4] Add `me recipes show <recipe> [--vault] [--json] [--full]` subcommand in `src/synapse_memory/cli.py` — depends on T011
- [ ] T046 [US4] Implement plain-text table formatter (no `rich` dependency) for `me recipes list` per [cli-contracts.md §2](./contracts/cli-contracts.md) — depends on T044
- [ ] T047 [US4] Implement JSON envelope helper `recipes_cli_envelope(ok, data, errors)` used by both `list --json` and `show --json` — depends on T044, T045

**Checkpoint**: US4 fully functional. Discoverability 확보.

---

## Phase 7: User Story 5 — Backward compatibility wrappers (Priority: P3)

**Goal**: 기존 `draft_resume`, `decide`, `what_did_i_think` 외부 함수 시그니처와 CLI stdout/exit code 가 framework 도입 후에도 변하지 않음. `what-did-i-think --timeline` 과 `--hybrid` 는 recipe pipeline 진입 금지.

**Independent Test**: 기존 `tests/test_endpoints_me*.py` 가 **무수정** 으로 모두 green. `me what-did-i-think --timeline` 출력이 framework 도입 전후 byte-identical (SC-008).

### Test-First (RED)

- [ ] T048 [P] [US5] Write failing test `tests/test_endpoints_me_compat.py::test_what_did_i_think_timeline_byte_identical` — fixture 에 ProjectCard 3 개, `--timeline` 호출 → output 이 002-timeline-recall 의 contract fixture 와 byte-identical (recipe pipeline 우회 증명)
- [ ] T049 [P] [US5] Write failing test `tests/test_endpoints_me_compat.py::test_decide_signature_preserved` — `decide(situation, top_k, model, ai_env, store, vault_path)` 시그니처 인트로스펙션 + return type 필드 set 보존
- [ ] T050 [P] [US5] Write failing test `tests/test_endpoints_me_compat.py::test_what_did_i_think_hybrid_path_unchanged` — `--hybrid` 호출 시 `hybrid_search` 가 1 회 호출되고 recipe pipeline `generate` 는 호출되지 않음

### Implementation (GREEN)

- [ ] T051 [US5] Refactor `decide()` in `src/synapse_memory/endpoints/me.py` to wrapper invoking `recipes.pipeline.generate("decide", {"situation": ...})` — preserve external signature (depends on T014)
- [ ] T052 [US5] Refactor distance-mode `what_did_i_think()` in `src/synapse_memory/endpoints/me.py` to wrapper invoking `recipes.pipeline.generate("recall", {"topic": ...})` — keep timeline branch + hybrid branch unchanged (depends on T014)
- [ ] T053 [P] [US5] Add builtin recipe `src/synapse_memory/recipes/builtin/decide.md` mirroring existing `DECIDE_SYSTEM` text + Profile injection (already present in legacy decide)
- [ ] T054 [P] [US5] Add builtin recipe `src/synapse_memory/recipes/builtin/recall.md` mirroring existing `WHAT_DID_I_THINK_SYSTEM` text for distance-mode only
- [ ] T055 [US5] Delete obsolete constants `DECIDE_SYSTEM`, `WHAT_DID_I_THINK_SYSTEM`, `RESUME_SYSTEM` from `endpoints/me.py` after T030/T051/T052 ship and tests pass

**Checkpoint**: 기존 사용자에게 완전 투명. `tests/test_endpoints_me*.py` 무수정 green.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 문서·observability·SC 검증·constitution 컴플라이언스.

- [ ] T056 [P] Update `docs/commands.md` with `me generate`, `me recipes list`, `me recipes show` synopses and link to [quickstart.md](./quickstart.md)
- [ ] T057 [P] Add 1-line note to `docs/architecture.md` describing `synapse_memory.recipes` subpackage and pointing to [data-model.md](./data-model.md)
- [ ] T058 [P] Update `AGENTS.md` "Active feature" line to 007-me-recipes if still pointing elsewhere
- [ ] T059 [P] Write `tests/test_recipes_sc_acceptance.py` end-to-end run binding spec SCs to test cases — SC-001 (new user recipe in 60 s), SC-002 (4 builtins produce non-empty md), SC-003 (en preferred → 0 Korean headers), SC-004 (Profile injection 100%), SC-006 (50 recipes ≤ 1 s), SC-007 (malformed isolation), SC-008 (timeline byte-identical)
- [ ] T060 [P] Verify SC-005 by running full existing pytest suite (no modifications to `tests/test_endpoints_me*.py`) — if any test broke during refactor, fix wrapper not the test
- [ ] T061 Run [quickstart.md](./quickstart.md) manually on dev machine, capture stdout to `specs/007-me-recipes/quickstart-smoke.md` (date-stamped, similar to 006's pattern)
- [ ] T062 [P] Add observability snapshot in `docs/development.md`: example stderr line + interpretation table — link to constitution Principle V
- [ ] T063 Final lint + `python -m pytest -x` green on a clean clone

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 시작 즉시 가능, 의존성 없음
- **Phase 2 (Foundational)**: Phase 1 완료 후 — 모든 user story 의 blocking prerequisite
- **Phase 3 (US1)**: Phase 2 완료 후 — MVP
- **Phase 4 (US2)**: Phase 2 완료 후 — US1 과 독립 실행 가능 (인력 있으면 병렬)
- **Phase 5 (US3)**: Phase 2 완료 후 — US1/US2 와 독립
- **Phase 6 (US4)**: Phase 2 완료 후 — US3 와 일부 fixture 공유하나 코드 독립
- **Phase 7 (US5)**: Phase 2 완료 후 — wrapper 이므로 Phase 4 가 먼저 끝나면 자연스러우나 기술적으로는 Phase 2 만 있으면 시작 가능
- **Phase 8 (Polish)**: 위 모든 phase 완료 후

### User Story Dependencies

- **US1 (P1)**: Phase 2 의존만. US2~US5 와 독립.
- **US2 (P1)**: Phase 2 의존만. US1 과 독립 (각자 다른 빌트인 recipe + 다른 fixture variant).
- **US3 (P2)**: Phase 2 의존만. user-over-builtin 동작은 US1 의 weekly_report 와 무관.
- **US4 (P2)**: Phase 2 + (선택) US3 의 user recipe fixture 가 있으면 list 검증이 풍부해짐. 기술적으로는 Phase 2 만 있으면 가능.
- **US5 (P3)**: Phase 2 만 있으면 시작 가능하나, US2 의 resume wrapper 가 먼저 끝나면 코드 충돌 없음. Phase 4 → Phase 7 직렬 권장.

### Within Each Story

- TDD 강제 — RED 테스트 (`T###` 의 첫 묶음) 가 모두 실패하는 것을 먼저 확인한 뒤 implementation tasks 진입.
- 모델·dataclass 먼저 → 서비스/오케스트레이터 → CLI 진입점 → 관측성/로그.
- 한 story 의 모든 task 가 green → checkpoint → 다음 story.

### Parallel Opportunities

- Phase 1 의 T002, T003 병렬.
- Phase 2 의 T004-T008 (모두 다른 테스트 파일) 병렬.
- Phase 2 의 T009·T015 병렬 (CompanyCard 변경은 recipe 코어와 독립).
- Phase 3 의 T017·T018 병렬; T019 도 별도 markdown 이라 T020 과 병렬.
- Phase 4 의 T025-T028 모두 다른 test case 라 병렬.
- Phase 7 의 T053·T054 병렬 (서로 다른 recipe markdown).
- Phase 8 의 T056-T060, T062 대부분 병렬.

---

## Parallel Example: User Story 1 (Phase 3)

```bash
# 모든 RED 테스트를 한 번에 작성 (각자 다른 파일):
Task: "Write failing test tests/test_recipes_generate.py::test_weekly_report_end_to_end"
Task: "Write failing test tests/test_recipes_cli.py::test_me_generate_weekly_report"

# 그 다음 RED 검증 후 GREEN 구현:
Task: "Create builtin recipe src/synapse_memory/recipes/builtin/weekly_report.md"
Task: "Build fixture content under tests/fixtures/recipes_vault/"
# CLI 변경 (T021-T023) 은 cli.py 단일 파일이라 직렬
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1) 완료.
2. **STOP**: 빌트인 `weekly_report` recipe 가 fixture vault 에서 작동, last_answer 갱신 확인.
3. demo / 자체 dogfooding 후 다음 phase 진입 결정.

### Incremental Delivery

1. **MVP** (Phase 1-3): weekly_report 만으로도 framework 가치 입증.
2. **+ Resume universality** (Phase 4): 디자이너/연구자/해외 채용 사용자 확보. v0.5 알파 후보.
3. **+ User extensibility** (Phase 5): 오픈소스 사용자의 자기 workflow 자유도 확보.
4. **+ Discoverability** (Phase 6): UX 완성.
5. **+ Backward compatibility** (Phase 7): 기존 사용자·기존 hook 깨짐 0.
6. **+ Polish** (Phase 8): 문서·관측성·SC 회귀 가드.

### Parallel Team Strategy (1 인 개발 가정 하 sequential)

본 프로젝트는 1 인 개발이라 phase 직렬 진행이 자연스럽다. 단일 phase 내부에서는
[P] 표시된 task 들을 한 묶음으로 `/speckit-implement` 에 위임 가능.

---

## Notes

- [P] 표시는 같은 phase 안에서 다른 파일·의존성 없는 task. 다른 phase 간에는 blocking 관계를 우선시.
- [Story] 라벨은 traceability — PR 본문에서 "Closes US3" 같이 인용.
- 각 user story 가 끝날 때마다 **independent test** 가 green 인지 확인하고 commit.
- TDD 원칙 (constitution III): RED 묶음의 모든 테스트가 실패하는 것을 먼저 확인 → implementation → GREEN → 필요 시 refactor.
- 회피: 모호한 task ("어디서 무엇을 한다" 가 불명), 같은 파일 동시 수정 충돌, user story 간 깨지는 cross-dependency.
- spec 의 SC 들이 polish phase 의 `test_recipes_sc_acceptance.py` 에 매핑되어 최종 acceptance gate 역할을 한다.
