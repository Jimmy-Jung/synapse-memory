# CLI Contracts: Cost Observability

## `synapse-memory cost summary [--days N] [--by command|model] [--json]`

- **분류**: batch
- **기본값**:
  - `--days 30`
  - `--by command`
  - table output
- **인자**:
  - `--days N`: 1 이상 정수. 현재 시각 기준 최근 N일 event 만 포함한다.
  - `--by command|model`: group key 선택.
  - `--json`: 사람이 읽는 표 대신 JSON object 출력.
- **Exit**:
  - `0`: 정상 출력, 또는 matching event 없음.
  - `1`: invalid argument, unreadable log 복구 실패.

## Table Output

```text
Cost summary (last 30 days, by command)
GROUP                    CALLS   INPUT  OUTPUT      USD   ELAPSED
ask                          3    1200     540   0.0031      12.4s
daily.generate               1    4200    1800   0.0098      33.7s
TOTAL                        4    5400    2340   0.0129      46.1s
```

No data:

```text
데이터 없음 — 아직 기록된 cost event 가 없습니다.
```

## JSON Output

```json
{
  "days": 30,
  "by": "command",
  "generated_at": "2026-05-12T10:00:00Z",
  "total": {
    "calls": 4,
    "input_tokens": 5400,
    "output_tokens": 2340,
    "usd": 0.0129,
    "elapsed_s": 46.1
  },
  "groups": [
    {
      "group": "ask",
      "calls": 3,
      "input_tokens": 1200,
      "output_tokens": 540,
      "usd": 0.0031,
      "elapsed_s": 12.4,
      "first_seen": "2026-05-11T09:00:00Z",
      "last_seen": "2026-05-12T09:00:00Z"
    }
  ]
}
```

## Validation

- `--days <= 0` 이면 stderr 에 `--days must be >= 1` 를 출력하고 exit 1.
- 알 수 없는 `--by` 값은 argparse choice error 로 exit 2.
- `--json` 출력은 stdout 에 JSON 만 출력한다.

## Slash Shim

`commands/synapse-cost.md` 는 다음 CLI 를 호출한다.

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory cost summary "$@"
```

응답을 대화에 붙일 때는 table 또는 JSON 원문을 유지한다.
