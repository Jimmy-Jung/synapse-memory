---
description: 일일 통합 워크플로 — 실패 stage 격리, resume, DailyReport. 첫 호출은 --quick 권장.
argument-hint: [--quick] [--profile-facts-only] [--resume-from <stage>]
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory daily $ARGUMENTS`

위 출력은 daily 파이프라인(collect_claude_code → collect_obsidian → classify → generate → index → update_profile → report)의 단계별 진행 결과입니다. 각 step의 성공/실패/건너뜀, 소요 시간, skip reason, DailyReport 경로를 요약하고, 실패한 step이 있으면 다음 재개 명령을 제안하세요.

## 모드

**`--quick` (권장 — 첫 호출 및 매일 routine)**

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily --quick
```

- 최근 7일 modified 노트만 mirror (mtime cutoff)
- classify 최대 10 cluster (AI 호출 cap)
- `update_profile` auto-skip (heavy AI)
- 첫 호출 ~3분 목표. 이후 매일 호출은 더 짧음 (incremental)

**Full (별도 호출 — 매주 1회 또는 작가 판단)**

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily
```

- 전체 vault scan + 모든 신규 cluster classify + update_profile 포함
- ⚠ ChromaDB write 동시성 회피를 위해 `--quick` 과 *동시* 실행 금지

## 재개 / 부분 실행 예

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily --resume-from classify
SYNAPSE_FROM_AGENT=1 synapse-memory daily --dry-run --resume-from index
SYNAPSE_FROM_AGENT=1 synapse-memory daily --quick --quick-days 14
```
