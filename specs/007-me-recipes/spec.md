# Feature Specification: Me Generator Recipes

**Feature Branch**: `007-me-recipes`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "me 모듈을 endpoint-per-feature 패턴에서 recipe-based generator framework 로 재설계한다. 이력서·카드뿐 아니라 보고서·학습자료·일기·회고록·브레인스토밍 등 사용자 vault 메모리(ProjectCard, CompanyCard, Profile, DecisionPatterns) 기반 결과물 생성을 universal·user-aware 하게 지원한다. 오픈소스 사용자가 코드를 고치지 않고 markdown 한 장으로 자기만의 결과물 종류를 추가할 수 있어야 한다."

## Clarifications

### Session 2026-05-12

- Q: CompanyCard 의 `resume_language` 필드를 본 feature 에서 추가할지 → A: 본 feature 에서 optional 필드로 추가하고 `draft_resume` locale precedence 1 순위로 사용
- Q: 사용자 recipe markdown 의 schema 진화 정책 → A: version 필드 없음. unknown 필드 무시, missing optional 은 default, missing required 만 fail. Breaking change 는 release notes 로 안내
- Q: Recipe system prompt 의 placeholder 표면 범위 → A: `{locale}, {domain}, {today}` + input_schema keys 만. Profile·RAG 결과는 user prompt 끝에 자동 첨부되며 system prompt 의 placeholder 로 노출되지 않음
- Q: System prompt 크기 상한을 어디서 확정할지 → A: 32KB 로 spec FR-016 에 확정. 초과 시 loader 가 해당 recipe 를 거부
- Q: Recipe 로딩·캐싱 정책 → A: CLI 호출마다 stateless fresh scan. 영속 캐시·file watcher 없음. 미래 daemon mode 가 생기면 별도 spec 으로 진화

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 주간 보고를 vault 메모리만으로 자동 생성 (Priority: P1)

사용자는 `synapse-memory me generate weekly_report --period=2026-W19` 한 줄로 그 주의 ProjectCard 활동과 사용자 Profile(말투·강점·지향)을 종합한 주간 보고 markdown 을 `vault/30_Creative/Reports/` 아래에 자동 저장할 수 있어야 한다. 톤은 Profile 의 voice 에 맞춰져야 한다.

**Why this priority**: 이 사용자 시나리오 하나만 동작해도 "vault 메모리 기반 결과물 생성" 이라는 핵심 가치가 입증된다. 이력서가 아닌 도메인에서도 second brain 이 도움이 됨을 보여주는 최소 MVP 다.

**Independent Test**: fixture vault 에 ProjectCard 2개 + `90_System/AI/Profile.md` 1개를 두고 `generate("weekly_report", {"period": "2026-W19"})` 를 호출한다. 결과 markdown 이 `30_Creative/Reports/` 아래에 저장되고, AI 호출 prompt capture 에 Profile 본문 + ProjectCard citations 가 모두 포함됨을 검증한다.

**Acceptance Scenarios**:

1. **Given** vault 에 Profile.md 와 그 주의 ProjectCard 2건이 존재한다, **When** 사용자가 `me generate weekly_report --period=2026-W19` 를 실행한다, **Then** markdown 출력이 stdout 으로 표시되고 `30_Creative/Reports/Weekly Report - 2026-W19.md` 가 저장된다.
2. **Given** vault 에 Profile.md 가 없다, **When** 사용자가 같은 명령을 실행한다, **Then** Profile 없이 ProjectCard 만 사용한 결과가 생성되고 `profile_used=false` 가 last_answer 에 기록된다.
3. **Given** 해당 period 에 매칭되는 카드가 0건이다, **When** 명령을 실행한다, **Then** "관련 카드 없음" 안내가 명확히 표시되고 빈 파일이 생성되지 않는다.

---

### User Story 2 - 이력서가 사용자 voice·언어·도메인을 인식 (Priority: P1)

사용자가 `synapse-memory me draft-resume <company_id>` 로 이력서를 만들 때, 사용자 Profile 이 자동 주입되고 회사 카드의 `resume_language` 또는 Profile 의 `preferred_lang` 에 따라 출력 언어가 결정되며, 사용자 도메인(소프트웨어/디자인/연구/PM 등)에 맞는 섹션 구조가 선택된다. 디자이너·연구자·해외 채용 사용자도 같은 명령으로 자기에게 맞는 이력서를 받을 수 있다.

**Why this priority**: 현재 RESUME_SYSTEM 이 "한국 IT 채용 시장" 으로 도메인을 하드코딩하고 한국어를 강제하는 점은 오픈소스 배포의 최대 장벽이다. P1 이지만 weekly_report 와 독립적으로 출시 가능하다.

**Independent Test**: Profile.md frontmatter 에 `preferred_lang: en, domain: design` 을 둔 fixture 와 CompanyCard 1건을 두고 `draft_resume("acme_co")` 를 호출한다. 출력 markdown 에 한국어 섹션 헤더가 0개이고, 디자인 도메인 섹션(케이스 스터디 / 도구 / 임팩트)이 포함됨을 검증한다.

**Acceptance Scenarios**:

1. **Given** Profile.preferred_lang="en" 과 CompanyCard 가 존재한다, **When** 사용자가 `me draft-resume <id>` 를 실행한다, **Then** 출력이 영어로 생성되고 system prompt 에 Profile 본문이 포함된다.
2. **Given** Profile.domain="research" 가 설정되어 있다, **When** 동일 명령을 실행한다, **Then** 출력 섹션이 "Publications / Grants / Methodology" 구조이고 "기술 스택" 섹션이 없다.
3. **Given** Profile.md 가 없고 CompanyCard 에도 `resume_language` 가 없다, **When** 명령을 실행한다, **Then** 기본 한국어 + generic 도메인으로 fallback 한다.

---

### User Story 3 - 사용자가 자기만의 결과물 종류를 코드 수정 없이 추가 (Priority: P2)

사용자는 `vault/90_System/AI/recipes/` 에 `my_diary.md` 같은 markdown 한 장 (frontmatter + system prompt 본문) 을 추가하기만 하면, 그 즉시 `me generate my_diary --topic=...` 로 실행할 수 있어야 한다. 빌트인 recipe 와 동일한 RAG + Profile 주입 + 저장 파이프라인을 자동으로 탄다.

**Why this priority**: 오픈소스 사용자의 자기 workflow 자유도를 결정짓는 핵심 가치. P1 두 가지가 동작해도 이 기능이 없으면 framework 가 아니라 "기능 3개짜리 도구" 일 뿐이다.

**Independent Test**: 빈 vault 에 `90_System/AI/recipes/diary.md` 를 한 장 만들고 (frontmatter: name/input_schema/save_subpath, 본문: system prompt) `me recipes list` 로 표시되는지, `me generate diary --topic=오늘회고` 로 실행 결과가 정상 저장되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 사용자가 `vault/90_System/AI/recipes/diary.md` 를 새로 추가한다, **When** `me recipes list` 를 실행한다, **Then** "diary" 가 출력 목록에 포함된다 (서버 재시작 불필요).
2. **Given** 빌트인 `journal` 과 사용자 `90_System/AI/recipes/journal.md` 가 동시에 존재한다, **When** `me generate journal ...` 를 실행한다, **Then** 사용자 recipe 가 우선 사용되고 출력 끝에 "user override" 표시가 last_answer 메타에 기록된다.
3. **Given** 사용자 recipe 의 frontmatter 에 필수 필드(`name`, `system_prompt_path` 또는 본문)가 빠져 있다, **When** loader 가 그 파일을 읽는다, **Then** 그 recipe 한 개만 명확한 에러와 함께 skip 되고 나머지 recipe 들은 정상 로드된다.

---

### User Story 4 - 가용 recipe 와 입력 schema 를 CLI 로 확인 (Priority: P2)

사용자는 `me recipes list` 로 모든 가용 recipe (빌트인 + 사용자) 와 각 description 을 보고, `me recipes show <name>` 으로 한 recipe 의 input schema·RAG filter·저장 경로·system prompt 미리보기를 확인할 수 있어야 한다.

**Why this priority**: 사용자가 어떤 결과물을 만들 수 있는지 발견(discoverability)과, 새 recipe 를 만들 때 참고 패턴을 빠르게 보는 용도. 핵심 기능은 아니지만 framework 의 사용성을 좌우한다.

**Independent Test**: 빌트인 4 개 + 사용자 1 개 = 5 개 recipe 가 있는 vault 에서 `me recipes list` 가 5 개 항목을 표 형태로 표시하고, `me recipes show weekly_report` 가 input_schema·rag_filter·save_subpath·system prompt 첫 20 줄을 출력하는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 빌트인 4 개 + 사용자 1 개 recipe 가 있다, **When** `me recipes list` 를 실행한다, **Then** 5 행 표가 출력되고 각 행에 name·description·source(builtin/user)·required inputs 가 표시된다.
2. **Given** 사용자가 존재하지 않는 recipe 이름으로 `me recipes show foo` 를 실행한다, **When** loader 가 해당 이름을 못 찾는다, **Then** 사용 가능한 가까운 이름 1~3 개를 제안한다.

---

### User Story 5 - 기존 명령·함수 backward compatibility (Priority: P3)

기존 `draft_resume`, `what_did_i_think`, `decide` 외부 함수 시그니처와 CLI 사용 패턴은 framework 도입 후에도 깨지지 않아야 한다. 내부 구현은 `generate()` 위의 얇은 wrapper 로 재구성될 수 있다.

**Why this priority**: 기존 사용자·기존 테스트·기존 hook 가 동작을 유지해야 점진적 마이그레이션이 가능하다. 새 framework 도입의 진입 장벽을 0 으로 만든다.

**Independent Test**: 기존 pytest 의 `tests/test_endpoints_me*.py` 를 변경 없이 실행해서 모두 green 인지, 기존 CLI subcommand 호출이 동일 stdout/exit code 인지 검증한다.

**Acceptance Scenarios**:

1. **Given** 기존 `me draft-resume`, `me what-did-i-think`, `me decide` CLI 진입점이 사용된다, **When** framework 도입 후 동일 인자로 실행한다, **Then** stdout·exit code·저장 경로가 도입 전과 동일하다.
2. **Given** 기존 단위 테스트 모음을 그대로 실행한다, **When** framework 코드가 머지된 상태이다, **Then** 회귀 없이 모두 통과한다.
3. **Given** `me what-did-i-think --timeline` 모드를 호출한다, **When** framework 도입 후 동일 명령을 실행한다, **Then** 002-timeline-recall 의 분기 그룹화·LLM 미호출 contract 가 그대로 유지된다 (recipe pipeline 으로 라우팅 안 됨).

---

### Edge Cases

- 사용자 recipe markdown 에 frontmatter 누락 또는 YAML parse error → 그 recipe 만 skip, 나머지 로드, 명확한 경고.
- 빌트인 recipe 와 사용자 recipe 가 같은 이름 → 사용자 우선 (last_answer 메타에 override 표시).
- `me generate <unknown>` → 가용 recipe 이름과 가장 가까운 후보 제안.
- recipe 의 `input_schema` 에서 required 인자가 누락되어 호출됨 → fail-fast, 누락 필드 목록을 에러로 표시.
- `save_subpath` 디렉터리가 없으면 자동 생성. 권한 없으면 명확한 에러.
- Profile.md 없음 → `use_profile=true` recipe 도 정상 실행되되 last_answer 에 `profile_used=false` 기록.
- locale/domain 감지 실패 → 기본값 (한국어 / generic) 으로 fallback, 출력 frontmatter 에 detection_source 표기.
- RAG matched 0 건 → recipe 별 fallback 메시지 또는 빈 결과로 명확히 종료, 빈 파일을 저장하지 않음.
- AI provider 호출 실패 → 기존 ask/decide 와 동일한 에러 표면, last_answer 에 기록하지 않음.
- 사용자 recipe 파일이 매우 큼 (>32KB system prompt) → loader 가 시스템 프롬프트 크기 상한을 넘는 recipe 를 거절.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define a `GenerationRecipe` abstraction with fields: name, description, system prompt template, input schema (required+optional), RAG filter, RAG top_k, use_profile flag, save subpath, locale_aware flag, domain_aware flag.
- **FR-002**: System MUST expose a single `generate(recipe_name, inputs, *, model, ai_env, store, vault_path)` entry point that performs profile load → locale detect → domain detect → RAG search → prompt compose → LLM call → optional save → last_answer record, in that order.
- **FR-003**: Recipes MUST be loaded from `vault/90_System/AI/recipes/` (user) with precedence over `src/synapse_memory/recipes/` (built-in). User recipes with the same name override built-in recipes.
- **FR-004**: System MUST ship at minimum the following built-in recipes for the initial release: `resume`, `weekly_report`, `journal`, `brainstorm`. Additional built-ins (monthly_report, study_note, retrospective, decision_log, interview_prep) MAY be added but are not required for completion.
- **FR-005**: Locale detection MUST follow precedence: explicit `--language=` CLI arg → CompanyCard `resume_language` field (if relevant) → Profile.md `preferred_lang` frontmatter → default `한국어`.
- **FR-006**: Domain detection MUST follow precedence: explicit `--domain=` CLI arg → Profile.md `domain` frontmatter → top tag frequency from matched ProjectCards → `generic` fallback.
- **FR-007**: `draft_resume` MUST inject Profile/DecisionPatterns text into the LLM system or user prompt and MUST NOT hardcode "한국 IT" or any single industry vocabulary in its default system prompt.
- **FR-008**: External function signatures of `draft_resume`, `decide`, and `what_did_i_think` MUST be preserved. Internal implementation MAY be refactored as wrappers over `generate()`.
- **FR-009**: System MUST expose CLI commands `me generate <recipe> [--key=value …]`, `me recipes list`, `me recipes show <recipe>`.
- **FR-010**: User-defined recipes added to `vault/90_System/AI/recipes/` MUST be discoverable by `me generate` and `me recipes list` without code changes, restarts, or any registration step. Recipe loading MUST be stateless per CLI invocation: each command scans both user and built-in recipe directories fresh on startup. The system MUST NOT maintain a persistent recipe cache, file watcher, or background daemon for recipe loading. Evolving to in-memory caching for future daemon/MCP-server modes is out of scope for this feature.
- **FR-011**: Every recipe execution that triggers an AI call MUST produce a `last_answer` record compatible with existing `AnswerCitation`/`AnswerReference` schema so existing follow-up flows (`--cite` style) work uniformly.
- **FR-012**: When a recipe declares `save_subpath`, the output MUST be written under the vault at that path. Filename MUST be deterministic from recipe name + primary input + ISO date.
- **FR-013**: `me what-did-i-think --timeline` mode MUST remain unchanged and MUST NOT route through the recipe pipeline (preserves 002-timeline-recall locked contract).
- **FR-014**: When required inputs declared in a recipe's `input_schema` are missing at call time, the system MUST fail fast before any LLM call with an error listing the missing fields.
- **FR-015**: Recipe loader MUST validate frontmatter against a minimum schema (name, description, system_prompt presence, save_subpath optional). Malformed recipes MUST be rejected individually with a descriptive log line; remaining recipes MUST load normally. Unknown frontmatter fields MUST be ignored without warning, missing optional fields MUST fall back to documented defaults, and only missing required fields MUST cause an individual recipe to be rejected. Recipes do not declare a `schema_version`; backward compatibility across releases is maintained at the loader level and breaking changes are communicated via release notes.
- **FR-016**: System MUST reject any recipe whose rendered system prompt exceeds 32 KB (32,768 bytes UTF-8) to prevent runaway LLM cost or context overflow. The size is measured after placeholder substitution. Rejected recipes MUST be reported individually with a descriptive log line; remaining recipes MUST load normally.
- **FR-017**: `me recipes list` output MUST distinguish built-in vs user recipes and show each recipe's required input names.
- **FR-018**: `me recipes show <name>` MUST output the recipe's name, description, input schema, RAG filter, save subpath, and a preview of the system prompt template.
- **FR-019**: Recipe template substitution MUST support exactly the documented placeholder set in system prompts: `{locale}`, `{domain}`, `{today}`, plus user-defined keys declared in the recipe's `input_schema`. Profile text and RAG-matched card content MUST NOT be exposed as system-prompt placeholders; they MUST be appended by the generator to the user prompt as fixed blocks. Template substitution MUST be simple string replacement and MUST NOT execute arbitrary code embedded in recipe markdown.

### Key Entities

- **GenerationRecipe**: Declarative spec for one task type. Holds name, description, system prompt template, input schema, RAG filter/top_k, use_profile flag, save_subpath, locale_aware/domain_aware flags. Loaded from markdown (frontmatter + body).
- **RecipeRegistry**: Loader that scans built-in and user recipe directories, validates frontmatter, resolves name conflicts (user wins), and exposes lookup/list operations.
- **GenerationContext**: Transient per-call object holding resolved locale, resolved domain, profile text, RAG matches, and rendered prompt. Used for prompt composition and for last_answer metadata.
- **GenerationResult**: Output bundle containing recipe name, rendered answer markdown, saved_path (or None), source ids cited, profile_used flag, locale, domain.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can add a new recipe markdown file to `vault/90_System/AI/recipes/` and successfully execute it via `me generate <name>` in under 60 seconds without making any code change.
- **SC-002**: Built-in recipes `resume`, `weekly_report`, `journal`, `brainstorm` all produce non-empty markdown output and save to their declared paths in a fixture vault end-to-end test.
- **SC-003**: For a fixture where Profile.preferred_lang is `en`, the generated resume contains zero Korean section headers and the AI prompt capture contains the Profile body text.
- **SC-004**: Every recipe execution with `use_profile=true` and a non-empty Profile.md is verified (via prompt capture) to include the Profile text in the AI prompt — measured at 100% of such recipe runs in the test suite.
- **SC-005**: The existing `me draft_resume`, `me decide`, and `me what_did_i_think` pytest suites pass after the framework is introduced. External API (function signatures, return types, CLI stdout / exit code) MUST remain byte-identical for existing callers. Internal mock targets in test setups MAY be updated minimally where they reach into implementation details (e.g., `patch.object(me_mod.ai_api, "complete", ...)` → `patch("synapse_memory.recipes.pipeline.ai_api_complete", ...)`); such mock-only edits do not constitute behavior changes.
- **SC-006**: `me recipes list` returns within 1 second in a vault containing up to 50 recipes (built-in + user).
- **SC-007**: A recipe with a malformed frontmatter does not block other recipes from loading; the failure is surfaced as a single warning line.
- **SC-008**: `me what-did-i-think --timeline` output for the same fixture is byte-identical before and after the framework lands (proves the timeline path is not routed through the new pipeline).

## Assumptions

- Existing `_load_profile_text` helper (or an equivalent that reads `90_System/AI/Profile.md`, `DecisionPatterns.md`, `DecisionQualityRegistry.md`) is reused; no vault schema migration is required by this feature.
- Profile.md frontmatter MAY optionally include `preferred_lang` and `domain` fields. Their absence falls back to documented defaults.
- CompanyCard schema includes an optional `resume_language` field as part of this feature. Its absence falls back to Profile.preferred_lang → default. This is the documented locale precedence 1 source in FR-005.
- 002-timeline-recall contracts remain locked; this feature does not modify them or their tests.
- 006-raw-rag-hybrid hybrid retrieval is independent; generic recipes use the existing dense `store.query` retriever unless a recipe explicitly opts into hybrid (out of scope for first release).
- LLM provider abstraction (`ai_api.complete`) is reused; no new provider integration is in scope.
- Recipe markdown loading uses standard YAML frontmatter parsing; no DSL or templating engine beyond simple `{placeholder}` substitution is in scope.
- Recipe size limit and placeholder set are confirmed at spec level: 32 KB system prompt cap (FR-016), placeholders `{locale}`, `{domain}`, `{today}` plus user-declared input_schema keys (FR-019).
- "user override" detection for name-conflict resolution and domain detection rely on best-effort heuristics; perfect classification is not required.
