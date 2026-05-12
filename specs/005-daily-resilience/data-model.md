# Data Model: Daily Resilience

## DailyStage

- **역할**: daily pipeline 의 실행 가능한 한 단계와 dependency contract 를 나타낸다.
- **저장 위치**: 없음. 코드 상수로 정의된다.

### Fields

| Field | Type | Required | Notes |
|---|---|---:|---|
| `name` | string | yes | CLI 에 노출되는 stable stage id |
| `description` | string | yes | dry-run/report 에 표시되는 짧은 설명 |
| `requires` | list[string] | yes | 이 stage 실행 전에 성공해야 하는 upstream stage |
| `action` | callable | yes | stage body |

### Validation

- `name` 은 unique 해야 한다.
- `requires` 의 모든 값은 존재하는 stage 이름이어야 한다.
- dependency cycle 은 허용하지 않는다.

## StageResult

- **역할**: 한 stage 의 실행 또는 skip 결과.
- **생성자**: `run_daily()`
- **저장 위치**: DailyReport markdown 에 요약 형태로 기록된다.

### Fields

| Field | Type | Required | Notes |
|---|---|---:|---|
| `name` | string | yes | stage id |
| `status` | string | yes | `success`, `failed`, `skipped` |
| `elapsed_s` | number | yes | skipped 는 0.0 |
| `summary` | string | no | counters 또는 산출물 요약. raw body 금지 |
| `error` | string | no | failed 일 때 사용자에게 필요한 짧은 오류 |
| `skip_reason` | string | no | skipped 일 때 upstream failure 또는 resume reason |

### State Rules

- `success`: `error` 와 `skip_reason` 이 비어 있어야 한다.
- `failed`: `error` 가 비어 있으면 안 된다.
- `skipped`: `skip_reason` 이 비어 있으면 안 되고 `elapsed_s=0.0` 이어야 한다.

## DailyResult

- **역할**: 한 daily run 의 전체 결과.
- **생성자**: `run_daily()`

### Fields

| Field | Type | Required | Notes |
|---|---|---:|---|
| `steps` | list[StageResult] | yes | 선택된 stage 전체. resume 이전 skip 포함 |
| `total_elapsed_s` | number | yes | 전체 wall-clock |
| `resume_from` | string/null | no | 사용자가 지정한 resume target |
| `report_path` | string/null | no | DailyReport write 성공 시 path |
| `report_error` | string/null | no | DailyReport write 실패 시 짧은 오류 |

### Derived Values

- `errors`: `status == failed` count
- `skipped`: `status == skipped` count
- `ok`: errors == 0 and report write policy does not force failure

## DailyReport

- **역할**: daily 실행 결과를 vault 에 남기는 사람이 읽는 markdown 감사 기록.
- **저장 위치**: `<vault>/90_System/AI/DailyReports/YYYY-MM-DD.md`

### Frontmatter

| Field | Type | Notes |
|---|---|---|
| `date` | string | local date |
| `total_elapsed_s` | number | one decimal place |
| `errors_count` | integer | failed stage count |
| `skipped_count` | integer | skipped stage count |
| `new_cards` | integer | summary 에서 파생 가능하면 기록, unknown 은 0 |
| `new_facts` | integer | summary 에서 파생 가능하면 기록, unknown 은 0 |
| `est_usd` | number | cost summary 에서 당일 총합, unavailable 은 0 |

### Body

- `## Stage Summary` table: stage, status, elapsed, summary, reason
- `## Failures`: failed stage 목록
- `## Resume`: resume-from 사용 시 재개 범위 설명

## CIWorkflow

- **역할**: PR/main 에서 quality gates 를 실행하는 repository automation.
- **저장 위치**: `.github/workflows/ci.yml`

### Required Checks

- pytest 전체 테스트
- ruff check
- mypy strict 대상
- local-only binaries 없이 통과
