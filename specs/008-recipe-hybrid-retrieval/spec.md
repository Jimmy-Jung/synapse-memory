# Feature Specification: Recipe Hybrid Retrieval

> **SUPERSEDED_BY_PROVIDER_ONLY / HISTORICAL ONLY**
>
> 이 문서는 provider-only 전환 전의 과거 설계 기록입니다. 현재 recipe/persona/ask
> 검색은 local hybrid ranking이 아니라 CardIndex + provider 선별 경로를 사용합니다.
> 현재 source of truth는 `specs/020-provider-only-retrieval/design.md`입니다.

**Feature Branch**: `008-recipe-hybrid-retrieval`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "recipe markdown frontmatter 에 옵셔널 `rag_mode: dense | hybrid` 필드 추가. pipeline.generate() 가 rag_mode=hybrid 면 006 의 hybrid_search 를 호출하고, 그 결과를 dense 와 동일한 인터페이스로 다운스트림에 전달. BM25 sidecar 미존재 시 명확한 에러 (`rag index --include-raw` 안내). `--rag-mode` CLI 인자도 추가하여 recipe 기본을 override 가능. 기존 dense-only recipe 들은 동작 변경 없음 (default `dense`)."

## Clarifications

### Session 2026-05-12

- Q: hybrid 미가용 시 자동 dense fallback vs 명시적 에러? → A: 명시적 에러. silent dense fallback 금지이며 오류 메시지에는 `synapse-memory rag index --include-raw` 재실행 안내가 포함된다.
- Q: hybrid RRF k 값은 006의 60 그대로 사용 vs recipe 별 override? → A: 006과 동일하게 RRF k=60 고정. recipe별 override는 이번 feature 범위 밖이다.
- Q: `rag_mode`가 `domain_aware`와 어떻게 상호작용하는가? → A: hybrid 결과도 dense 결과와 동일한 matched record 인터페이스로 전달되며, domain 추론은 기존 tags 기반 로직을 그대로 사용한다.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recipe가 hybrid retrieval을 선택한다 (Priority: P1)

Recipe 작성자는 `weekly_report`처럼 고유명사 recall이 중요한 recipe에서 frontmatter 한 줄로 hybrid retrieval을 켤 수 있어야 한다. 사용자는 기존 `me generate weekly_report` 흐름을 유지하면서 회사명, 사람 이름, 프로젝트 slug 같은 정확 키워드가 더 잘 반영된 결과를 얻는다.

**Why this priority**: 007 recipe framework의 가치는 task별 retrieval 전략을 선언할 수 있을 때 커진다. dense-only는 의미 유사도에는 강하지만 고유명사 recall에서 약할 수 있으므로, recipe 단위 opt-in이 MVP다.

**Independent Test**: 임시 vault에 `rag_mode: hybrid` recipe와 proper-noun fixture를 두고 `me generate`를 실행한다. hybrid retrieval path가 호출되고, downstream prompt와 `source_ids`는 dense 결과와 같은 형태로 유지되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** recipe frontmatter에 `rag_mode: hybrid`가 있다, **When** 사용자가 `synapse-memory me generate <recipe>`를 실행한다, **Then** dense-only store query 대신 hybrid retrieval 결과가 recipe prompt에 전달된다.
2. **Given** hybrid 결과에 ProjectCard tags가 포함된다, **When** recipe가 `domain_aware: true`다, **Then** domain 추론은 기존 tag frequency 규칙으로 동일하게 동작한다.
3. **Given** recipe frontmatter에 `rag_mode`가 없다, **When** 사용자가 기존 recipe를 실행한다, **Then** dense retrieval 기본값이 유지되고 stdout, save path, last_answer 형식은 변경되지 않는다.

---

### User Story 2 - CLI에서 recipe 기본 retrieval mode를 override한다 (Priority: P2)

사용자는 recipe 파일을 수정하지 않고도 일회성으로 `--rag-mode dense|hybrid`를 지정할 수 있어야 한다. 이를 통해 같은 recipe를 dense와 hybrid로 비교하거나, sidecar 상태가 의심될 때 dense로 명시 실행할 수 있다.

**Why this priority**: recipe 기본값만 있으면 실험과 디버깅이 불편하다. CLI override는 기존 declarative recipe 모델을 유지하면서 운영 편의성을 제공한다.

**Independent Test**: `rag_mode: dense` recipe를 `--rag-mode hybrid`로 실행하고, `rag_mode: hybrid` recipe를 `--rag-mode dense`로 실행한다. 각각 CLI override가 frontmatter보다 우선하는지 검증한다.

**Acceptance Scenarios**:

1. **Given** recipe 기본값이 dense다, **When** 사용자가 `--rag-mode hybrid`를 지정한다, **Then** 해당 호출은 hybrid retrieval을 사용한다.
2. **Given** recipe 기본값이 hybrid다, **When** 사용자가 `--rag-mode dense`를 지정한다, **Then** 해당 호출은 dense retrieval을 사용한다.
3. **Given** 사용자가 허용되지 않은 mode를 입력한다, **When** CLI가 인자를 파싱한다, **Then** 명확한 사용법 오류와 non-zero exit code를 반환한다.

---

### User Story 3 - Hybrid 미가용 상태를 명확히 보고한다 (Priority: P3)

사용자는 BM25 sidecar가 없거나 006 hybrid index가 준비되지 않은 상태에서 hybrid recipe를 실행하면, dense-only로 조용히 fallback된 결과가 아니라 무엇을 해야 하는지 알 수 있는 오류를 받아야 한다.

**Why this priority**: silent fallback은 사용자가 hybrid 품질을 믿고 의사결정하는 상황에서 잘못된 신뢰를 만든다. 006의 fallback 정책과 recipe framework의 관측성을 맞춰야 한다.

**Independent Test**: BM25 sidecar가 없는 isolated L0에서 `rag_mode: hybrid` recipe를 실행한다. 명령은 실패하고 stderr에 sidecar 미존재와 `rag index --include-raw` 안내가 포함되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** BM25 sidecar가 없다, **When** hybrid recipe가 실행된다, **Then** 명령은 실패하고 `synapse-memory rag index --include-raw` 실행을 안내한다.
2. **Given** hybrid dependency가 현재 target branch에 없다, **When** implementation이 시작된다, **Then** 006 raw-rag-hybrid 산출물 병합 또는 rebase를 먼저 요구한다.
3. **Given** hybrid retrieval 중 오류가 난다, **When** CLI가 오류를 표시한다, **Then** dense fallback으로 성공 처리하지 않는다.

### Edge Cases

- `rag_mode` 값이 `dense` 또는 `hybrid`가 아니면 해당 recipe만 validation error로 거부되고 다른 recipe는 계속 로드된다.
- `--rag-mode` CLI override는 recipe frontmatter보다 우선하지만, 호출 1회에만 적용되고 recipe 파일을 수정하지 않는다.
- RAG match가 0건이면 기존 recipe fallback/error 정책을 유지한다. retrieval mode만으로 빈 결과 정책을 바꾸지 않는다.
- Hybrid 결과에 raw chunk가 포함되어도 외부 LLM prompt에는 006이 보장한 redacted document만 전달된다.
- `me what-did-i-think --timeline`은 recipe pipeline에 들어오지 않으며 이번 feature가 timeline 정렬 계약을 변경하지 않는다.
- Current `main` does not contain `006-raw-rag-hybrid`; implementation must first land or base on those artifacts before code work begins.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Recipe markdown frontmatter MUST accept optional `rag_mode` with allowed values `dense` and `hybrid`.
- **FR-002**: Missing `rag_mode` MUST default to `dense` for all existing built-in and user recipes.
- **FR-003**: Recipe loader MUST reject invalid `rag_mode` values with an isolated recipe validation error.
- **FR-004**: `synapse-memory me generate <recipe>` MUST accept `--rag-mode dense|hybrid` and use it as the highest-precedence retrieval mode for that invocation.
- **FR-005**: `pipeline.generate()` MUST accept an optional retrieval mode override equivalent to the CLI override.
- **FR-006**: When the effective mode is `dense`, generation MUST preserve existing dense retrieval behavior and downstream data shape.
- **FR-007**: When the effective mode is `hybrid`, generation MUST use the existing 006 hybrid retrieval contract and adapt results to the same downstream matched-record interface used by dense retrieval.
- **FR-008**: Hybrid retrieval MUST use RRF k=60 and MUST NOT introduce recipe-level RRF override in this feature.
- **FR-009**: If BM25 sidecar or hybrid retrieval prerequisites are unavailable, generation MUST fail with a clear error that includes `synapse-memory rag index --include-raw`; it MUST NOT silently fall back to dense.
- **FR-010**: `domain_aware` resolution MUST consume hybrid matched records through the same tags-based path used for dense matched records.
- **FR-011**: Hybrid matched records MUST preserve source ids and metadata required by prompt citations and `last_answer`.
- **FR-012**: External LLM prompts MUST receive only redacted text from hybrid results; this feature MUST NOT bypass 006 raw redaction guarantees.
- **FR-013**: Existing `tests/test_endpoints_me*.py` behavior MUST remain green, including timeline bypass behavior.
- **FR-014**: `me.generate.<recipe>` observability MUST indicate the effective retrieval mode so smoke captures can distinguish dense and hybrid runs.
- **FR-015**: Documentation MUST explain recipe `rag_mode`, CLI `--rag-mode`, default behavior, and hybrid-unavailable remediation.

### Key Entities *(include if feature involves data)*

- **Recipe Retrieval Mode**: The effective retrieval strategy for one recipe invocation. It is resolved from CLI override, recipe frontmatter, then default `dense`.
- **GenerationRecipe**: Existing recipe declaration extended with optional retrieval mode.
- **GenerationContext**: Runtime state for one generation, extended to remember the effective retrieval mode and matched records.
- **Matched Record**: Existing downstream pair of searchable record and distance-like score. Hybrid results must be adapted into this shape without losing metadata.
- **Hybrid Availability Error**: User-facing failure state for missing BM25 sidecar or unavailable hybrid dependency.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Existing recipes without `rag_mode` produce the same generated prompt construction order, save path, and last_answer metadata as dense mode in automated tests.
- **SC-002**: A `rag_mode: hybrid` fixture recipe calls hybrid retrieval and passes at least two matched records into the prompt in an automated integration test.
- **SC-003**: CLI `--rag-mode` override wins over recipe frontmatter in both directions (`dense → hybrid`, `hybrid → dense`) in automated tests.
- **SC-004**: Missing BM25 sidecar produces a non-zero CLI result and stderr includes `rag index --include-raw`.
- **SC-005**: Domain-aware hybrid fixture resolves domain from matched record tags using the same expected output as dense fixture.
- **SC-006**: `tests/test_endpoints_me*.py` and all `tests/test_recipes_*.py` remain green.
- **SC-007**: Full `python3 -m pytest` remains green before implementation is considered complete.

## Assumptions

- 006 raw-rag-hybrid is the canonical provider of BM25 sidecar loading, hybrid search, and redacted raw retrieval guarantees.
- If 006 is not on the target branch at implementation time, the implementation branch must first merge/rebase onto 006 or land 006 into `main`.
- Recipe framework remains the owner of prompt composition, save path, profile injection, locale/domain resolution, and last_answer recording.
- This feature does not add raw indexing defaults to `daily`; hybrid remains opt-in through recipe config or CLI override.
- This feature does not modify 002 timeline recall sorting or route timeline mode through recipes.
