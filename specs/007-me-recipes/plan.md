# Implementation Plan: Me Generator Recipes

**Branch**: `007-me-recipes` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/007-me-recipes/spec.md`

## Summary

`me` 모듈을 endpoint-per-feature 패턴에서 **markdown-recipe 기반 generator framework** 로 재설계한다.
하나의 단일 entry point `generate(recipe_name, inputs)` 가 Profile 로드 → 언어 감지 → 도메인 감지 →
RAG 검색 → 프롬프트 합성 → LLM 호출 → 선택적 vault 저장 → `last_answer` 기록을 일관 처리한다.
빌트인 recipe (`resume`, `weekly_report`, `journal`, `brainstorm`) 4 종을 첫 release 로 제공하며,
사용자는 `vault/90_System/AI/recipes/` 에 markdown 한 장 추가만으로 자기만의 결과물 종류를
코드 변경 없이 추가할 수 있다. 기존 `draft_resume` / `decide` / `what_did_i_think` 는 `generate()`
위의 wrapper 로 재구현되어 backward compatibility 를 유지한다.

기술 접근: spec 의 Clarifications 에서 5 개 결정이 lock 되어 있음 — CompanyCard 에 optional
`resume_language` 필드 추가, recipe markdown 은 `schema_version` 없는 best-effort 로딩, system
prompt placeholder = `{locale}/{domain}/{today}` + input_schema keys 만, system prompt 32 KB 상한,
CLI 호출마다 stateless fresh scan. 추가 plan-level 결정 (LLM timeout, frontmatter 정확한 키 이름,
도메인별 섹션 set, 파일명 규칙) 은 Phase 0 research 에서 일괄 처리한다.

## Technical Context

**Language/Version**: Python 3.11 (constitution platform floor)
**Primary Dependencies**: 기존 모듈 재사용 — `synapse_memory.llm.ai_api`, `synapse_memory.rag.VectorStore`,
`synapse_memory.cards.company`, `synapse_memory.storage.last_response`,
`synapse_memory.collectors.obsidian.mirror.get_vault_path`. 새 의존성 — `PyYAML` (recipe frontmatter
파싱; 기존 deps 에 포함되어 있는지 research 에서 확인. 없으면 도입).
**Storage**: vault markdown (recipes, 결과 저장), 기존 ChromaDB (RAG), 기존 `last_response` JSON.
새 영속 상태 없음.
**Testing**: `pytest` — 단위 (`test_recipes_loader`, `test_recipes_generate`,
`test_recipes_locale_domain`), wrapper backward-compat (`test_endpoints_me_compat`), CLI
(`test_recipes_cli`). 기존 `tests/test_endpoints_me*.py` 는 수정 없이 green 유지 (SC-005).
**Target Platform**: macOS 26.0 (Tahoe) + Apple Silicon, CLI process model.
**Project Type**: Python library + CLI (`synapse-memory` console script).
**Performance Goals**: `me recipes list` ≤ 1 s @ 50 recipes (SC-006); recipe load+parse 대당
≤ 20 ms; system prompt 32 KB hard cap (FR-016, Q4).
**Constraints**:
- Stateless per-invocation recipe loading (Q5/FR-010): file watcher, in-process cache, daemon 금지.
- LLM provider 는 `ai_api.complete` 만 사용; 직접 외부 호출 금지 (constitution Principle II).
- `me what-did-i-think --timeline` 은 recipe pipeline 으로 라우팅 금지 (FR-013).
- 기존 외부 함수 시그니처 보존 (FR-008).
**Scale/Scope**: 빌트인 recipe 4 종 + 사용자 recipe ~수십 개. 사용자 1 인. CLI 단일 프로세스.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|-----------|--------|------|
| I. Local-First & Privacy by Default | ✅ PASS | 모든 recipe markdown 은 vault 내부. 외부 LLM 호출은 기존 `ai_api.complete` 만 사용 — 새 외부 경로 추가 없음. Profile/Cards 본문이 prompt 에 포함되지만 기존 endpoint (`decide`) 와 동일 정책. |
| II. Two-Pass Redaction (NON-NEGOTIABLE) | ✅ PASS | feature 가 새 외부 출력 경로를 만들지 않음. `ai_api.complete` 의 기존 redaction 파이프라인을 그대로 통과. redaction 우회 코드 없음. eval 회귀 영향 없음. |
| III. Test-First Discipline (NON-NEGOTIABLE) | ✅ PASS | tasks 단계에서 모든 신규 모듈을 Red → Green → Refactor 로 발주. 기존 `test_endpoints_me*` 무수정 (SC-005). |
| IV. Conversation-Context-Aware Endpoints | ✅ PASS | `me generate <recipe>` 는 **interactive** 분류 (LLM 호출 + 사용자 voice 의존). TTY 가드 + 3 초 안내 + `SYNAPSE_FROM_AGENT=1` bypass 적용. `me recipes list` / `me recipes show` 는 **batch** 분류 (LLM 미호출, TTY 가드 없음). |
| V. Reproducible Daily Pipeline & Observability | ✅ PASS | `daily` 파이프라인 미수정. `me generate` 는 idempotency 의무 대상 아님 (사용자 의도적 생성 액션). 로그 1 줄 요약 (recipe·duration·source_ids 수) 으로 관측성 추가. |

**Result**: ALL GREEN. Complexity Tracking 항목 없음.

## Project Structure

### Documentation (this feature)

```text
specs/007-me-recipes/
├── plan.md                              # This file
├── research.md                          # Phase 0 — 결정 사항·근거·대안
├── data-model.md                        # Phase 1 — GenerationRecipe / Registry / Context / Result
├── quickstart.md                        # Phase 1 — 사용자 따라하기 시나리오 5분
├── contracts/
│   └── cli-contracts.md                 # Phase 1 — me generate / recipes list / recipes show 명세
├── checklists/
│   └── requirements.md                  # /speckit-specify 산출물
└── tasks.md                             # /speckit-tasks 산출물 (NOT created here)
```

### Source Code (repository root)

```text
src/synapse_memory/
├── endpoints/
│   └── me.py                            # 기존 — draft_resume / decide / what_did_i_think
│                                        #   wrapper 로 generate() 위로 reroute. timeline 경로 미변경.
├── recipes/                             # 신규 — generator framework
│   ├── __init__.py                      #   public API: generate, list_recipes, show_recipe
│   ├── recipe.py                        #   GenerationRecipe, GenerationResult, GenerationContext
│   ├── registry.py                      #   RecipeRegistry — stateless fresh scan, user-over-builtin
│   ├── loader.py                        #   markdown frontmatter 파싱, 32KB cap, validation
│   ├── locale.py                        #   locale precedence (--language → CompanyCard.resume_language → Profile → 기본)
│   ├── domain.py                        #   domain precedence (--domain → Profile.domain → tag freq → generic)
│   ├── pipeline.py                      #   generate() core: profile → locale → domain → RAG → prompt → LLM → save → last_answer
│   └── builtin/                         #   빌트인 recipe markdown 4 종 (resume, weekly_report, journal, brainstorm)
│       ├── resume.md
│       ├── weekly_report.md
│       ├── journal.md
│       └── brainstorm.md
├── cards/
│   └── company.py                       # 기존 — CompanyCard 에 optional `resume_language` 필드 추가 (Q1)
└── cli.py                               # 기존 — `me generate / recipes list / recipes show` 서브커맨드 추가

tests/
├── test_recipes_loader.py               # frontmatter parse / 32KB cap / required vs optional / malformed skip
├── test_recipes_registry.py             # user-over-builtin / fresh scan / unknown-recipe suggestion
├── test_recipes_locale.py               # locale precedence 4 단
├── test_recipes_domain.py               # domain precedence 3 단
├── test_recipes_generate.py             # end-to-end fixture vault → markdown 결과 + last_answer
├── test_recipes_cli.py                  # me generate / recipes list / recipes show stdout · exit code
├── test_endpoints_me_compat.py          # 기존 draft_resume/decide/what_did_i_think 시그니처 보존 (SC-005)
└── fixtures/
    └── recipes_vault/                   # ProjectCard 2 + Profile.md + 빈 recipes dir 시나리오
```

**Structure Decision**: 단일 Python 패키지 (`synapse_memory`) 내부에 `recipes/` 서브패키지를 신설.
기존 `endpoints/me.py` 는 외부 시그니처를 유지한 채 `recipes.pipeline.generate()` 를 호출하는
얇은 wrapper 로 변환. CompanyCard 에 `resume_language: Optional[str]` 한 필드만 추가 (Q1).

## Phase 0 (Research) — Outputs

다음 항목은 spec Clarifications 에서 lock 되지 않은 implementation detail 로 [research.md](./research.md)
에서 단일 표로 정리한다. 각 항목은 Decision / Rationale / Alternatives 형태.

- LLM timeout / retry 정책 (기존 `draft_resume` 의 240 초, `decide` 의 120 초 와 정합)
- Recipe frontmatter 정확한 키 이름 (yaml schema): `name`, `description`, `input_schema`,
  `rag_filter`, `rag_top_k`, `use_profile`, `save_subpath`, `locale_aware`, `domain_aware`
- Profile.md 의 optional frontmatter 키 (`preferred_lang`, `domain`)
- 도메인별 섹션 set (software / design / research / pm / generic) 의 정확한 헤더 라인
- 결과 파일명 규칙 (예: `{recipe_name} - {primary_input} ({YYYY-MM}).md`)
- `last_answer` command 식별자 (`me.generate.<recipe_name>` 형태)
- `me what-did-i-think` 의 `--hybrid` (006) 와 recipe pipeline 의 RAG 호출 경로 분리 방식
- `me generate` 의 TTY 가드 적용 위치 (CLI layer vs pipeline)
- `PyYAML` 신규 의존성 여부 — 이미 deps 에 포함되어 있는지 확인 (없으면 도입 필요)

## Phase 1 (Design) — Outputs

- [data-model.md](./data-model.md) — `GenerationRecipe`, `RecipeRegistry`, `GenerationContext`,
  `GenerationResult` 의 정확한 필드 / 관계 / 검증 규칙 / lifecycle.
- [contracts/cli-contracts.md](./contracts/cli-contracts.md) — `me generate <recipe>`,
  `me recipes list`, `me recipes show <recipe>` 의 input / output / exit code / 에러 코드.
- [quickstart.md](./quickstart.md) — 빈 vault → Profile.md 추가 → `weekly_report` 실행 →
  사용자 recipe `diary.md` 추가 → `me generate diary` 실행 까지 5 분 walkthrough.

## Phase 1 Post-Design Constitution Re-Check

Phase 1 산출물 작성 후 재평가 — 새 외부 경로·redaction 우회·daily 영향 모두 없음. ALL GREEN 유지.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

해당 없음. Constitution Check 가 모두 PASS 이므로 본 표는 비워둔다.
