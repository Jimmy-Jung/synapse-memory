---
description: 일일 통합 5분 워크플로 — 실패 stage 격리, resume, DailyReport 작성
argument-hint: [--profile-facts-only] [--resume-from <stage>]
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory daily $ARGUMENTS`

위 출력은 daily 파이프라인(collect_claude_code → collect_obsidian → classify → generate → index → update_profile → report)의 단계별 진행 결과입니다. 각 step의 성공/실패/건너뜀, 소요 시간, skip reason, DailyReport 경로를 요약하고, 실패한 step이 있으면 다음 재개 명령을 제안하세요.

예:

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily --resume-from classify
SYNAPSE_FROM_AGENT=1 synapse-memory daily --dry-run --resume-from index
```
