---
description: 일일 통합 워크플로 — 실패 stage 격리, resume, DailyReport. 기본은 full pipeline.
argument-hint: [--quick] [--watch-status] [--profile-facts-only] [--resume-from <stage>]
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory daily $ARGUMENTS`

위 출력은 daily 파이프라인의 단계별 진행 결과입니다.

파이프라인 흐름 (v0.15+):

1. **collect_* (17종 컬렉터)**: claude_code, codex, shell_history, cursor, continue, aider, git_self (opt-in), apple_notes, day_one, vscode_local_history, imessage (Full Disk Access), gmail_sent (opt-in), calendar, browser_history, screen_time, apple_health (drop-in), obsidian
2. **classify** (신규 cluster 분류) → **generate** (Card 생성) → **index** (RAG)
3. **update_profile** (Profile 후보 추출, full 모드만)
4. **report** (DailyReport 작성)

각 stage의 성공/실패/건너뜀, 소요 시간, skip reason, DailyReport 경로를 요약하고, 실패한 step이 있으면 다음 재개 명령을 제안하세요. 컬렉터별로 source 미존재 / 권한 부재면 자동 skip (errors 0 또는 짧은 안내 1줄) 되므로 실패가 아닙니다.

## 모드

**Full (기본 — 사용자가 인자를 명시하지 않은 경우)**

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily
```

- 전체 vault scan + 모든 신규 cluster classify + update_profile 포함
- ChromaDB write 동시성 회피를 위해 daily 중복 실행은 lock 으로 차단됩니다.

**`--quick` (명시 요청 시만)**

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily --quick
```

- 최근 7일 modified 노트만 mirror (mtime cutoff)
- classify 최대 10 cluster (AI 호출 cap)
- `update_profile` auto-skip (heavy AI)
- `--watch-status`를 붙이면 실행 중 `[daily-status] stage (n/22)` 진행률을 같이 출력
- 사용자가 "빠르게", "최근 변경분만", "`--quick`"을 명시한 경우에만 사용

## 재개 / 부분 실행 예

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory daily --resume-from classify
SYNAPSE_FROM_AGENT=1 synapse-memory daily --dry-run --resume-from index
SYNAPSE_FROM_AGENT=1 synapse-memory daily --quick --watch-status --quick-days 14
SYNAPSE_FROM_AGENT=1 synapse-memory daily-status --watch
SYNAPSE_FROM_AGENT=1 synapse-memory daily --skip collect_browser_history
```

## 종료 후 흐름 — apply 제안

daily가 정상 종료되고 `update_profile` 단계가 성공하면(즉 신규 `Profile-YYYY-MM-DD.md` 후보가 생성되면), AskUserQuestion으로 다음을 사용자에게 제안하세요.

> "오늘자 Profile 후보가 생성됐습니다. 지금 `/sm:apply-profile` 흐름으로 항목별 검토할까요?"
>
> A. 지금 검토 시작 (Yes)
> B. 나중에 (No)

A 선택 시 `/sm:apply-profile` 흐름으로 이어집니다. B 선택 시 일반 종료. 사용자가 옵션을 명시 선택하지 않은 상태로는 apply 자동 진입 금지 — Constitution VI Installation Consent 준수.

`--dry-run` 모드이거나 `update_profile` 단계가 실패·skip이면 이 제안을 생략하세요 (신규 후보가 없음).

## 종료 후 흐름 — 낮은 신뢰도 후보 검토 제안

`update_profile` 이 **신규 fact/pattern 0건** 으로 끝났는데 ledger awaiting 합계가 0보다 크다면 (예: `[ledger ... | awaiting fact=27 pattern=29]`), 추출은 됐지만 promotion 임계치(`fast_path_confidence`, 기본 0.90)를 못 넘은 후보가 쌓여 있다는 뜻입니다.

이 경우 AskUserQuestion으로 다음을 제안하세요.

> "오늘 신규 Profile 후보는 임계치(0.90)를 못 넘었습니다. 추출된 후보(awaiting N건)는 있지만 신뢰도가 낮아 자동 추천을 미뤘습니다. **어느 신뢰도까지 직접 검토하시겠어요?**"
>
> A. 0.85 이상 검토 (관대 — noise 약간 늘 수 있음)
> B. 0.80 이상 검토 (더 관대 — review 가짓수 많음)
> C. 검토 안 함 (그대로 두기, 며칠 더 daily 누적)

선택에 따라 다음 명령을 실행하세요 (먼저 `--dry-run` 으로 후보 수만 확인하면 안전):

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory profile-review-awaiting --min-confidence 0.85 --dry-run
# 후보 수가 합리적이면 dry-run 빼고 실행
SYNAPSE_FROM_AGENT=1 synapse-memory profile-review-awaiting --min-confidence 0.85
```

명령이 성공하면 `MemoryInbox/YYYY/MM/Profile-YYYY-MM-DD.md` 가 생성되므로, 이어서 위 "apply 제안" 흐름(`/sm:apply-profile`)으로 진행할지 다시 AskUserQuestion으로 물어보세요. dedupe / dismissed 안전망은 그대로 적용되므로 vault 진실원본과 중복되는 후보는 자동 제외됩니다.

`--quick` 모드이거나 ledger awaiting 합계가 0이면 이 제안을 생략하세요.
