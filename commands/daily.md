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

## 종료 후 흐름 — apply 제안

daily가 정상 종료되고 `update_profile` 단계가 성공하면(즉 신규 `Profile-YYYY-MM-DD.md` 후보가 생성되면), AskUserQuestion으로 다음을 사용자에게 제안하세요.

> "오늘자 Profile 후보가 생성됐습니다. 지금 `/sm:apply-profile` 흐름으로 항목별 검토할까요?"
>
> A. 지금 검토 시작 (Yes)
> B. 나중에 (No)

A 선택 시 `/sm:apply-profile` 흐름으로 이어집니다. B 선택 시 일반 종료. 사용자가 옵션을 명시 선택하지 않은 상태로는 apply 자동 진입 금지 — Constitution VI Installation Consent 준수.

`--dry-run` 모드이거나 `update_profile` 단계가 실패·skip이면 이 제안을 생략하세요 (신규 후보가 없음).
