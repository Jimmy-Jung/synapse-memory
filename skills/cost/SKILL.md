---
name: cost
description: Use when the user asks "내가 synapse-memory에 얼마 썼지?", "토큰 사용량", "비용 요약", "Claude/apfel 호출 cost". Aggregates cost.jsonl by command / model / date.
---

# /sm:cost — 비용·토큰 요약

`~/.synapse/private/cost.jsonl` 에 누적된 LLM / embedding 호출 로그를 집계합니다.

## 실행

```bash
synapse-memory cost summary --days 30 --by command
synapse-memory cost summary --by model --json
```

- `--by command`: 커맨드별 비용
- `--by model`: 모델별 비용
- `--json`: 기계 가공용 출력
