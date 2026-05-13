---
description: vault 청소 도우미 — 오래된·휴면·빈 자료를 archive 폴더로 *이동* (영구 삭제 0건)
argument-hint: (인자 없음) — 슬래시 안에서 대화형으로 카테고리 선택
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory cleanup scan --json`

위 출력은 vault read-only 스캔 결과입니다. **이동·삭제는 일절 일어나지 않았습니다** — 후보 목록만 본 상태.

다음 스크립트를 따라 진행하세요. **모든 실제 이동은 사용자 동의 후에만**.

## 1단계 — 후보 요약 보고

JSON의 `candidates`를 카테고리별로 묶어 사람 말로 정리하세요.

```
청소 후보 N건 — 영구 삭제 0건. 모두 vault 안 `40_Archive/_cleanup-YYYY-MM-DD/`로 이동만.

  inbox_stale         K건 — 00_Inbox에서 30일 이상 미정리 노트
  dormant_project     K건 — 90일간 변경 없는 프로젝트 폴더
  old_resume          K건 — 이력서 초안 90일 경과
  stale_memory_inbox  K건 — MemoryInbox 후보 60일간 옮겨지지 않음
  empty_card          K건 — 빈 draft 카드 (positions·keywords 모두 비어 있음)
  old_daily_report    K건 — DailyReport 90일 경과
  empty_folder        K건 — 빈 폴더
```

후보가 0건이면 "vault가 깨끗합니다. 청소 불필요." 한 줄 보고 후 종료.

## 2단계 — 카테고리 선택 (사용자 응답 대기)

```
어떤 카테고리를 정리할까요? 안전을 위해 한 번에 한 카테고리씩 진행하는 것을 권장합니다.

번호로 선택하세요 (다중 가능, 콤마 구분):
  1. inbox_stale
  2. dormant_project
  3. old_resume
  4. stale_memory_inbox
  5. empty_card
  6. old_daily_report
  7. empty_folder
  all  — 전부 일괄 (10건 미만일 때만 권장)
  skip — 오늘은 진행 안 함
```

응답 전 다음 단계로 넘어가지 마세요.

## 3단계 — 선택 카테고리에서 미리보기 + 동의

각 카테고리마다:

### 카테고리 안 후보가 5개 이하

파일 하나씩 보여주고 yes/no 받기.

```
[1/N] <source_path>
      reason: <reason>
      목적지: <target_path>
      이 항목을 archive로 옮길까요? (yes/no/skip-category)
```

### 카테고리 안 후보가 6개 이상

미리보기 3건 + 일괄 동의.

```
[<category>] N건 전체 미리보기:

  - <source_1> — <reason>
  - <source_2> — <reason>
  - <source_3> — <reason>
  ... 외 (N-3)건

전체 archive로 옮길까요? (yes-all / pick-each / skip-category)
```

`pick-each`를 선택하면 5개 이하 흐름으로 떨어집니다.

## 4단계 — 동의 받은 항목 실제 이동

`SYNAPSE_FROM_AGENT=1 synapse-memory cleanup apply --apply --category <선택한 카테고리들>` 실행.

> `--apply` 없이는 dry-run으로만 동작합니다. 사용자가 명시적으로 `yes`를 한 후에만 `--apply`를 붙이세요.

실행 결과에서 다음을 보고하세요.

- 이동된 건수
- 매니페스트 경로 (`90_System/AI/CleanupReports/YYYY-MM-DD.md`)
- 실패가 있으면 사유

## 5단계 — 매니페스트 + 롤백 안내

```
✓ <N건>을 `40_Archive/_cleanup-YYYY-MM-DD/`로 이동했습니다.

매니페스트(Obsidian에서 열어 검토 가능):
  90_System/AI/CleanupReports/YYYY-MM-DD.md

롤백이 필요하면 매니페스트의 "롤백 가이드" 절을 보세요. 셸 한 줄로 항목별 복구 가능.

다음에 다른 카테고리도 정리하려면 다시 `/synapse-cleanup`을 부르세요.
```

종료.

## 절대 하지 말 것

- ❌ `--apply` 없이도 archive 이동이 일어났다고 보고하기 (dry-run은 *예정*만)
- ❌ 사용자 동의 없이 `--apply`로 호출
- ❌ `40_Archive/` 안 파일을 *vault 밖으로* 옮기거나 *영구 삭제*
- ❌ `90_System/AI/Profile.md`, `DecisionPatterns.md`, `recipes/` 안 파일을 이동 후보로 보고
- ❌ frontmatter `pinned: true` / `cleanup: skip`이 있는 파일을 이동
- ❌ 한 세션에 카테고리 7개를 *전부 자동* 처리 (각 카테고리마다 동의 받기)

## 사용자 vault 안 보호 마커

사용자가 특정 파일을 *영구히* 청소 대상에서 제외하려면 frontmatter에 다음을 추가하면 됩니다 (안내만 — Synapse가 대신 추가하지 말 것).

```yaml
---
cleanup: skip
# 또는
pinned: true
---
```
