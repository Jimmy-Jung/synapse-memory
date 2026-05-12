# Phase 1 Data Model — Me Generator Recipes

**Feature**: 007-me-recipes
**Date**: 2026-05-12

본 문서는 [plan.md](./plan.md) 의 Phase 1 산출물 중 데이터 모델 부분이다.
모든 객체는 **in-memory / transient** — 영속 상태는 vault markdown (recipes 본체)
과 결과 출력 파일, 그리고 기존 `last_response` JSON 만이다.

## 1. `GenerationRecipe`

Recipe markdown 1 장을 파싱한 결과. immutable dataclass.

### Fields

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| `name` | `str` | ✅ | — | regex `^[a-z][a-z0-9_]{0,63}$` |
| `description` | `str` | ✅ | — | 1 ≤ len ≤ 200 |
| `source` | `Literal["builtin", "user"]` | ✅ | — | loader 가 origin 디렉터리에서 채움 |
| `source_path` | `Path` | ✅ | — | 절대경로, 표시용 (`me recipes show` 출력) |
| `input_schema` | `dict[str, Literal["required","optional"]]` | ✅ | — | 각 key 는 placeholder 식별자 |
| `rag_filter` | `dict[str, str] \| None` | optional | `None` | None 이면 store filter 없음 |
| `rag_top_k` | `int` | optional | `8` | 1 ≤ x ≤ 50 |
| `use_profile` | `bool` | optional | `True` | — |
| `save_subpath` | `str \| None` | optional | `None` | vault-relative, `..` 금지 |
| `locale_aware` | `bool` | optional | `True` | — |
| `domain_aware` | `bool` | optional | `False` | — |
| `timeout` | `int` | optional | `120` | 1 ≤ x ≤ 600 |
| `model` | `str` | optional | `"sonnet"` | `ai_api` 가 인식하는 alias |
| `system_prompt` | `str` | ✅ | — | rendered length ≤ 32 KB (UTF-8 bytes); markdown body |

### Validation rules

1. **Frontmatter parse** (loader 단계):
   - YAML 파싱 실패 → recipe 한 개 reject, 다른 recipe 정상 로드 (FR-015).
   - 필수 필드 누락 → reject.
   - unknown 필드 → 조용히 무시 (Q2).
2. **System prompt size** (loader 단계):
   - 미렌더 길이 + worst-case placeholder 길이 ≤ 32 KB (FR-016/Q4).
   - 초과 시 reject + log line.
3. **Save path safety** (`save_subpath` 가 set 인 경우):
   - 절대경로 금지, `..` 금지, NULL/줄바꿈 금지.
4. **Input schema** (호출 시점):
   - required key 가 inputs 에 없으면 LLM 호출 전 fail-fast (FR-014).
   - 사용자 입력의 type 은 문자열로 통일 (CLI 기반).

### Lifecycle

- 생성: `loader.parse_recipe(path) -> GenerationRecipe`
- 사용: `pipeline.generate()` 가 한 번 받고 사용 후 폐기
- 폐기: 프로세스 종료 (stateless, Q5)

## 2. `RecipeRegistry`

빌트인 + 사용자 recipe 디렉터리를 스캔해 `dict[str, GenerationRecipe]` 를 구성.

### Fields

| Field | Type | Note |
|-------|------|------|
| `recipes` | `dict[str, GenerationRecipe]` | name → recipe. user-over-builtin 적용 후. |
| `skipped` | `list[tuple[Path, str]]` | (경로, reject 사유) — `me recipes list --verbose` 에서 노출 |
| `builtin_dir` | `Path` | `src/synapse_memory/recipes/builtin/` |
| `user_dir` | `Path` | `<vault>/90_System/AI/recipes/` |

### Operations

- `scan()` — 두 디렉터리에서 `*.md` 발견 → loader → 검증 통과한 것만 dict 적재
  - 시간 복잡도 O(n) (n = recipe 수). SC-006 에서 50 recipes ≤ 1 s.
- `get(name) -> GenerationRecipe` — 없으면 `RecipeNotFoundError` (with 최대 3개
  근접 이름 제안, FR-018 의 AC2)
- `list() -> list[GenerationRecipe]` — name 알파벳 정렬

### State

- in-memory only. CLI 호출 1 회 = 새 RecipeRegistry 1 회 (Q5).
- 사용자 디렉터리 부재 시 (`vault/90_System/AI/recipes/` 없음) builtin 만 로드.

## 3. `GenerationContext`

`pipeline.generate()` 의 단일 호출 동안 만들어지는 working state.
recipe 와 입력을 결합한 결과를 담는다.

### Fields

| Field | Type | Note |
|-------|------|------|
| `recipe` | `GenerationRecipe` | 선택된 recipe |
| `inputs` | `dict[str, str]` | CLI 인자에서 normalize 된 값 (required + optional 완전) |
| `profile_text` | `str` | `_load_profile_text()` 결과. 빈 문자열 가능 |
| `profile_used` | `bool` | profile_text 가 비어 있지 않고 recipe.use_profile=True 인 경우만 True |
| `locale` | `str` | 예: `"한국어"`, `"English"` |
| `locale_source` | `Literal["cli","company_card","profile","default"]` | precedence 어느 단에서 결정되었는지 |
| `domain` | `str` | 예: `"software"`, `"generic"` |
| `domain_source` | `Literal["cli","profile","tags","default"]` | 동일 |
| `matched_records` | `list[tuple[VectorRecord, float]]` | RAG 결과 |
| `today` | `date` | placeholder `{today}` 의 source. CLI override 가능. |
| `rendered_system_prompt` | `str` | placeholder 치환 후 |
| `rendered_user_prompt` | `str` | profile + cards + inputs 자동 조립 |

### Construction order

```
1. inputs validate (recipe.input_schema 의 required)
2. profile_text = _load_profile_text(vault) if recipe.use_profile else ""
3. locale = resolve_locale(cli_arg, company_card, profile_text, default)
4. matched_records = rag.query(recipe.rag_filter, recipe.rag_top_k)
5. domain = resolve_domain(cli_arg, profile_text, matched_records, default)
6. rendered_system_prompt = recipe.system_prompt.format(locale=…, domain=…, today=…, **inputs)
   - 크기 ≤ 32KB 재검증 (사용자 입력으로 부풀려질 가능성)
7. rendered_user_prompt = compose_user_prompt(profile_text, matched_records, inputs)
```

## 4. `GenerationResult`

`generate()` 의 return value. immutable dataclass.

### Fields

| Field | Type | Note |
|-------|------|------|
| `recipe_name` | `str` | — |
| `answer_markdown` | `str` | LLM 출력 (postprocess 후) |
| `saved_path` | `Path \| None` | `save_subpath` 가 set 일 때만 |
| `source_ids` | `list[str]` | matched cards 의 `card_id` 모음, citation 용 |
| `profile_used` | `bool` | context 에서 그대로 복사 |
| `locale` | `str` | — |
| `domain` | `str` | — |
| `last_answer_ref` | `AnswerReference` | 기존 schema 재사용 (FR-011) |

## 5. CompanyCard 확장 — `resume_language`

Q1 결정의 단일 schema 변경.

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `resume_language` | `str \| None` | optional | `None` |

- 기존 CompanyCard frontmatter 파싱 (`cards.company.load_company_card`) 에 한 필드
  추가. 부재 시 `None` — locale precedence 의 2 순위 (Profile) 로 흐름.
- spec FR-005 의 locale 1 순위.

## 6. Relationships

```
            ┌──────────────────────┐
            │   RecipeRegistry     │
            │   (stateless scan)   │
            └──────────┬───────────┘
                       │ .get(name)
                       ▼
┌──────────────────────┐       ┌─────────────────────┐
│ GenerationRecipe     │──────▶│ GenerationContext   │──┐
│ (frozen dataclass)   │       │ (transient working) │  │
└──────────────────────┘       └──────────┬──────────┘  │
                                          │             │
                                          ▼             │
                               ┌────────────────────┐   │
                               │ ai_api.complete()  │   │
                               └──────────┬─────────┘   │
                                          │             │
                                          ▼             │
                               ┌────────────────────┐   │
                               │ GenerationResult   │◀──┘
                               │  + AnswerReference │
                               │  + saved markdown  │
                               └────────────────────┘
```

## 7. Out-of-scope (deferred)

- Recipe 의 multi-output (한 호출에 여러 markdown 생성) — 단일 출력만 지원.
- Recipe chaining (한 recipe 의 출력이 다른 recipe 의 input) — 사용자가 CLI 두
  번 호출해서 달성.
- Recipe 의 hybrid retrieval 노출 — research R-7 참고.
- Recipe versioning 필드 — Q2 결정에 따라 도입하지 않음.
