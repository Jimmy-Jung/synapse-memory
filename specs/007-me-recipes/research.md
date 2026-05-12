# Phase 0 Research — Me Generator Recipes

**Feature**: 007-me-recipes
**Date**: 2026-05-12

이 문서는 [plan.md](./plan.md) 의 "Phase 0 Outputs" 에 나열된 implementation-level
unknown 을 단일 표로 lock 한다. spec.md 의 Clarifications 5 건은 이미 결정되어
있으므로 본 표에는 포함하지 않는다.

각 결정: **Decision** (확정 사항) / **Rationale** (근거) / **Alternatives** (대안과
기각 이유).

---

## R-1 — LLM timeout / retry 정책

- **Decision**: recipe frontmatter 에 optional `timeout` 필드 (초). 미지정 시
  default 120 초. `ai_api.complete` 의 retry 는 기존 동작에 위임 (provider 별
  retry 정책 변경 없음). recipe `timeout` 상한은 600 초.
- **Rationale**: 기존 `draft_resume` 의 240 초·`decide` 의 120 초 가 이미 분기되어
  있는데, recipe 별 의도된 출력 길이가 다른 만큼 (resume: 길다, journal: 짧다)
  recipe 자체가 자신의 timeout 을 선언하는 게 자연스럽다. retry 는 LLM 호출
  layer 의 관심사라 recipe spec 에서 빼는 게 단일 책임 원칙에 부합.
- **Alternatives**:
  - 글로벌 fixed 120 초 — recipe 별 정당한 차이를 무시.
  - 글로벌 fixed 240 초 — 짧은 recipe 가 stalled provider 에서 오래 매달림.
  - recipe 별 retry 횟수까지 노출 — 표면 복잡도 증가, 효용 낮음.

## R-2 — Recipe frontmatter 키 이름

- **Decision**:

  | YAML key | 타입 | 필수 | 기본값 |
  |----------|------|------|--------|
  | `name` | str (kebab/snake) | required | — |
  | `description` | str (≤200자) | required | — |
  | `input_schema` | mapping `{key: required|optional}` | required | `{}` 도 허용 |
  | `rag_filter` | mapping `{metadata_key: value}` | optional | `null` (필터 없음) |
  | `rag_top_k` | int (1..50) | optional | `8` |
  | `use_profile` | bool | optional | `true` |
  | `save_subpath` | str (vault-relative path) | optional | `null` (stdout-only) |
  | `locale_aware` | bool | optional | `true` |
  | `domain_aware` | bool | optional | `false` |
  | `timeout` | int (1..600) | optional | `120` |
  | `model` | str (e.g. `sonnet`) | optional | `sonnet` |

  System prompt 본문은 frontmatter 다음의 markdown body 전체. 시스템에서
  `{locale}`, `{domain}`, `{today}` + `input_schema` 의 키들이 string 치환.
- **Rationale**: spec FR-001 의 필드 리스트와 1:1. 기존 코드 (`draft_resume` 의
  `top_k_projects`, `decide` 의 `top_k`) 와 변수명 정렬. `domain_aware` 만 default
  `false` — generic recipe (journal, brainstorm 등) 가 도메인 분기 없이 동작.
- **Alternatives**:
  - JSON schema 풀-스펙 (오버킬, 첫 release 에 부적합)
  - TOML / YAML 혼용 (단일 markdown frontmatter 가 단순)

## R-3 — Profile.md frontmatter 키

- **Decision**: Profile.md 는 optional frontmatter 로 `preferred_lang: str` 와
  `domain: str` 를 가질 수 있다. 둘 다 없어도 동작 (default fallback). 추가하는
  순간 자동 인식. 이 두 키 이외의 frontmatter 는 무시.
- **Rationale**: vault 의 사용자 데이터에 강제 마이그레이션 없이 점진 도입.
  Recipe pipeline 의 `locale_aware` / `domain_aware` 가 false 면 읽지도 않음.
- **Alternatives**:
  - 별도 `90_System/AI/preferences.yml` 로 분리 — vault 안에 새 파일 형태가
    하나 더 늘어남. Profile.md 의 frontmatter 가 이미 자연스러운 자리.

## R-4 — 도메인별 섹션 set (resume recipe)

- **Decision**: `resume` 빌트인 recipe 의 system prompt 에 다음 도메인 매트릭스를
  embed 한다 (Q3 의 placeholder 표면 안으로 모두 들어감 — `{domain}` 만 치환).

  | domain | section order |
  |--------|---------------|
  | `software` | 핵심 한 줄 / 핵심 경험 / 프로젝트 상세 / 기술 스택 / 기타 |
  | `design` | 핵심 한 줄 / 핵심 경험 / 케이스 스터디 (프로세스·도구·임팩트) / 도구·역량 / 기타 |
  | `research` | 핵심 한 줄 / 핵심 연구 / Publications / Grants & Awards / Methodology |
  | `pm` | 핵심 한 줄 / 핵심 경험 / 임팩트 사례 (문제·가설·결과·메트릭) / 협업·툴 |
  | `generic` | 핵심 한 줄 / 핵심 경험 / 주요 활동 상세 / 보유 역량 |

- **Rationale**: spec User Story 2 의 AC #2 (`Profile.domain="research"` 시 "Publications/Grants/Methodology" 출력) 와 직결. 5 종으로 한정해 검증 비용을 통제.
- **Alternatives**:
  - 도메인 무한 확장 (사용자 정의) — 일관된 채점 어려움. 사용자는 자기 `resume.md` recipe 를 직접 만들어 우회 가능 (FR-003).
  - 도메인 무시하고 모든 사용자에게 generic — Profile.domain 의 의미 상실.

## R-5 — 결과 파일명 규칙

- **Decision**: `{recipe.display_name} - {primary_input_value} ({YYYY-MM-DD}).md`.
  - `primary_input_value`: recipe `input_schema` 의 첫 required key 의 값
    (예: resume → `<display_name>`, weekly_report → `<period>`, journal → `<date>`,
    brainstorm → `<topic>`).
  - 파일명에 들어가는 사용자 값은 OS-safe 로 normalize (`/`, `\`, NUL, 줄바꿈 →
    하이픈; 길이 ≤ 80자).
  - 기존 동일 파일 존재 시 `... ({YYYY-MM-DD-HHmm}).md` 로 fallback (overwrite 금지).
- **Rationale**: 기존 `draft_resume` 의 `Resume - {company} ({YYYY-MM}).md` 패턴을
  일반화. 사용자가 vault 탐색기 (Obsidian) 에서 정렬 시 직관적.
- **Alternatives**:
  - UUID/타임스탬프 prefix — 사람이 못 읽음.
  - overwrite 허용 — 의도치 않은 데이터 손실.

## R-6 — `last_answer` command 식별자

- **Decision**: `me.generate.<recipe_name>` 형태. 예: `me.generate.weekly_report`.
  wrapper 가 호출하는 경로 (`draft_resume` → 내부 `generate("resume", ...)`) 도
  동일 식별자 `me.generate.resume` 를 사용한다 (기존 `me.draft_resume` 식별자는
  더 이상 기록되지 않음 — backward compat 는 함수 시그니처 레벨에서만).
- **Rationale**: SC-005 의 backward compat 는 "외부 함수 시그니처" 와 "stdout / exit
  code" 만 요구 (spec FR-008). `last_answer` 의 internal command tag 까지 보존
  하면 framework refactor 의 가치가 줄어든다.
- **Alternatives**:
  - 기존 식별자 유지 (`me.draft_resume`, `me.what_did_i_think`, `me.decide`) +
    새로 `me.generate.*` 병행 — 두 식별자가 혼재해 follow-up `--cite` 로직이
    복잡.

## R-7 — `me what-did-i-think` 의 `--hybrid` (006) 와 recipe pipeline 의 RAG 경로 분리

- **Decision**: recipe pipeline 의 RAG 호출은 `store.query(...)` 만 사용 (dense
  retrieval). `--hybrid` 같은 retrieval 플래그는 recipe 가 노출하지 않음.
  기존 `what_did_i_think` wrapper 만 `hybrid` 인자를 그대로 받아 wrapper 안에서
  `hybrid_search(...)` 를 호출하는 분기를 유지 (recipe pipeline 우회).
  `--timeline` 모드는 spec FR-013 대로 recipe pipeline 진입 자체를 안 함.
- **Rationale**: 006 의 hybrid retrieval 은 timeline contract 와 함께 이미
  `what_did_i_think` 에 고정된 contract. 첫 release 에는 recipe 표면을 단순하게
  유지. 미래에 hybrid 가 일반적으로 유용해지면 별도 spec 으로 `rag_mode: dense|hybrid`
  필드 추가 가능.
- **Alternatives**:
  - 모든 recipe 가 `--hybrid` 노출 — sidecar BM25 index 가 필요해 사용자 가
    `rag index` 를 안 했을 때 갑작스러운 실패. 첫 release 표면 줄임.

## R-8 — `me generate` TTY 가드 적용 위치

- **Decision**: CLI layer (`cli.py`) 에서 TTY 가드 + 3 초 안내 + `SYNAPSE_FROM_AGENT=1`
  bypass 를 처리. `recipes.pipeline.generate()` 자체는 TTY 무관하게 동작 (라이브러리
  층). `me recipes list` / `me recipes show` 는 가드 없음 (LLM 미호출, batch 분류).
- **Rationale**: constitution Principle IV 에서 가드는 CLI entrypoint 의 책임으로
  정의. 기존 `draft_resume` 의 CLI wrapper 가 같은 패턴.
- **Alternatives**:
  - pipeline 안에서 가드 — 라이브러리로 import 할 때 부수효과 생김.

## R-9 — PyYAML 신규 의존성

- **Decision**: 추가 도입 불요. `pyproject.toml` 에 이미 `PyYAML>=6.0` 등재 확인됨
  (예: `synapse_memory.cards.company`, `synapse_memory.cards.project` 가 이미 사용).
- **Rationale**: deps churn 회피.
- **Alternatives**: 없음.

---

## Open questions deferred to tasks / implementation phase

- 도메인 자동 감지의 tag 빈도 threshold (예: 최빈 tag 의 비율 ≥ 0.3 일 때만 채택,
  그 외 generic) — tasks 의 `test_recipes_domain.py` 에서 fixture 와 함께 lock.
- 빌트인 recipe markdown 의 정확한 prompt 텍스트 — tasks 에서 작성 시 결정.
  각 recipe 가 system prompt 32 KB 이내 (FR-016) 임을 단위 테스트로 보장.
- `me recipes list` 의 출력 폭 / 컬럼 정렬 — CLI 표 라이브러리 사용 여부는
  구현 단계 (현재 `rich` 미도입; plain text 표로 시작).
