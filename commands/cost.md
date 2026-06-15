---
description: 비용/토큰 요약 — Claude 호출 cost.jsonl 집계
argument-hint: summary --days 30 --by command | summary --by model --json
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory cost $ARGUMENTS`

Claude Code CLI 호출이 기록한 로컬 private cost log 를 집계합니다. 기본은 최근 30일 command 별 표 출력입니다.

예시:
- `summary`
- `summary --days 7 --by command`
- `summary --days 30 --by model --json`

`cost` 명령은 batch endpoint 입니다. 외부 LLM 호출 없이 `~/.synapse/private/cost.jsonl` 만 읽습니다.
