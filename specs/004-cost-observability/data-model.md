# Data Model: Cost Observability

## CostEvent

- **역할**: 외부 Claude/apfel subprocess 호출 1회를 나타내는 append-only 감사 row.
- **생성자**: `llm/claude.py::_run_claude`, `llm/apfel.py::_run_apfel`
- **저장 위치**: `~/.synapse/private/cost.jsonl`

### Fields

| Field | Type | Required | Notes |
|---|---|---:|---|
| `event_id` | string | yes | 시간 정렬 가능한 id (`YYYYMMDDTHHMMSSffffffZ-xxxx`) |
| `ts` | ISO-8601 UTC string | yes | 호출 종료 시각 |
| `command` | string | yes | CLI command family (`ask`, `me.what_did_i_think`, `daily.generate`, `unknown`) |
| `provider` | string | yes | `claude` 또는 `apfel` |
| `model` | string | yes | provider model alias 또는 envelope model |
| `status` | string | yes | `success`, `error`, `timeout`, `unavailable` |
| `input_tokens` | integer | yes | provider value 또는 heuristic estimate, unknown 은 0 |
| `output_tokens` | integer | yes | provider value 또는 heuristic estimate, unknown 은 0 |
| `usd` | number | yes | known estimate 또는 0 |
| `pricing_source` | string | yes | `provider`, `estimated`, `local_unpriced`, `unknown` |
| `elapsed_s` | number | yes | wall-clock seconds, 4 decimal places 권장 |
| `error_kind` | string/null | no | 실패 시 분류명. raw stderr/prompt 금지 |

### Validation

- `event_id`, `ts`, `command`, `provider`, `model`, `status`, `pricing_source` 는 비어 있을 수 없다.
- `provider` 는 `claude | apfel`.
- `status` 는 `success | error | timeout | unavailable`.
- token count 는 0 이상 정수다.
- `usd` 와 `elapsed_s` 는 0 이상 숫자다.
- raw prompt, raw response, card body, feedback reason, file content 를 담는 필드는 금지한다.

## CostSummaryGroup

- **역할**: `cost summary` 가 출력하는 파생 집계 row.
- **생성자**: `cost/summary.py`
- **저장 위치**: 없음. 호출 시 계산 후 stdout 출력.

### Fields

| Field | Type | Notes |
|---|---|---|
| `group` | string | command 또는 model |
| `calls` | integer | event count |
| `input_tokens` | integer | 합계 |
| `output_tokens` | integer | 합계 |
| `usd` | number | 합계 |
| `elapsed_s` | number | 합계 |
| `first_seen` | ISO-8601 string | 기간 내 첫 event |
| `last_seen` | ISO-8601 string | 기간 내 마지막 event |

## PricingRule

- **역할**: provider/model 별 deterministic 비용 산정 규칙.
- **생성자**: `cost/pricing.py`
- **저장 위치**: 코드 상수. 원격 fetch 없음.

### Rules

- Claude envelope 가 total cost 를 제공하면 provider 값을 우선한다.
- known model 단가가 있으면 token count 로 best-effort 산정한다.
- unknown/local model 은 `usd=0`, `pricing_source="unknown"` 또는 `"local_unpriced"` 를 사용한다.

## State Transitions

```text
external call starts
  -> subprocess returns success
      -> CostEvent(status=success) append
  -> subprocess exits non-zero
      -> CostEvent(status=error) append
      -> original exception behavior preserved
  -> subprocess timeout
      -> CostEvent(status=timeout) append
      -> original exception behavior preserved

cost summary
  -> load readable events
  -> if corrupt tail: backup tail and continue with prefix
  -> filter by days
  -> group by command/model
  -> render table or JSON
```
