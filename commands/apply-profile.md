---
description: MemoryInbox candidate 파일의 ProfileFact/DecisionPattern 항목을 AskUserQuestion으로 항목별 승인받아 Profile.md/DecisionPatterns.md에 반영. status: applied로 마감.
argument-hint: [date YYYY-MM-DD | --all-pending]
---

!`synapse-memory list-pending-profiles --json`

위 출력은 vault MemoryInbox의 `status: pending_review` 후보 목록 (JSON 배열, 오래된 순)입니다.

## 작업 흐름

당신은 다음 단계를 순서대로 수행하세요. 사용자 결정은 항상 AskUserQuestion으로 받습니다 (사용자 선호: plan-mode GUI).

### 1. 대상 후보 결정

- `$ARGUMENTS`에 날짜(`YYYY-MM-DD`)가 있으면 그 날짜를 선택. 없으면 위 JSON 배열에서 가장 최근(마지막) 항목 선택.
- `$ARGUMENTS`가 `--all-pending`이면 JSON 배열 전체를 오래된 순으로 순차 처리 (각 사이클이 끝나면 다음 날짜로).
- JSON이 비어 있으면 "pending 후보 없음" 안내 후 종료.

### 2. 후보 파일 읽기·파싱

선택된 후보 파일을 Read 도구로 읽고 다음 두 섹션을 항목으로 분리합니다.

- `## ProfileFact 후보` — 각 카테고리(`### {category}`) 아래 `- [confidence] 문장` 형식의 bullet. 모든 카테고리 합쳐 평탄화하되 카테고리 정보는 유지.
- `## DecisionPattern 후보` — `### {trigger}` 헤더 + 본문 `- 행동:`, `- 이유:`, `- 신뢰도:` 묶음. 1 trigger = 1 항목.

총 N개 항목(ProfileFact + DecisionPattern)을 모읍니다.

### 3. 항목별 AskUserQuestion (4개씩)

N개 항목을 4개 단위로 나눠 AskUserQuestion을 호출합니다. 각 항목은 단일 질문이고 다음 옵션을 제공합니다.

- `Yes` — Profile.md (해당 카테고리) 또는 DecisionPatterns.md (`## Approved Patterns`)에 그대로 추가
- `No` — skip
- `Edit` — 사용자가 수정 문구 입력 (별도 AskUserQuestion으로 받음)

질문 텍스트에는 카테고리, 신뢰도, 본문을 모두 포함해 사용자가 한눈에 판단할 수 있게 합니다.

### 4. 승인분 반영

- ProfileFact `Yes` (또는 Edit 결과): vault `Profile.md`의 해당 카테고리 섹션(예: `## Tech / Domain`) 끝에 bullet으로 Edit 도구로 추가
- DecisionPattern `Yes` (또는 Edit 결과): vault `DecisionPatterns.md`의 `## Approved Patterns` 섹션에 `### {trigger}` + 본문 추가
- `No`: 아무것도 안 함

vault Profile/Patterns 경로는 CLAUDE.md의 `90_System/AI/Profile.md`, `90_System/AI/DecisionPatterns.md` 기본값을 사용하거나, 사용자에게 위치를 묻습니다.

### 5. 후보 파일 마감

승인 단계가 끝나면 후보 파일 frontmatter를 Edit 도구로 갱신합니다.

```diff
-status: pending_review
+status: applied
+applied_date: <오늘 ISO 날짜>
```

### 6. 결과 요약

처리 완료 후 다음을 출력합니다.

- 총 N개 중 ✅ approved / ✏️ edited / ❌ skipped 개수
- 반영된 카테고리·패턴 목록
- 마감된 후보 파일 경로

`--all-pending`이면 다음 날짜의 후보로 이어집니다.

## 주의

- AskUserQuestion은 한 번에 최대 4 questions/call이므로 N>4면 자동 분할.
- 사용자가 중간에 중단하면 처리된 항목까지는 보존하되 후보 파일은 그대로 pending_review로 둘 것 (idempotent — 다시 호출하면 처음부터).
- vault Profile.md / DecisionPatterns.md가 없으면 사용자에게 알리고 신규 생성 동의를 받음.
