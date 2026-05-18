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

- `## ProfileFact 후보` — 각 카테고리(`### {category}`) 아래 `- [confidence] 문장` 형식의 bullet. 그 아래 `  ↳ ledger: N회 등장 ...` 라인이 있으면 누적 메타로 보존.
- `## DecisionPattern 후보` — `### {trigger}` 헤더 + 본문 `- 행동:`, `- 이유:`, `- 신뢰도:` (+ 선택적 `↳ ledger:`) 묶음. 1 trigger = 1 항목.

frontmatter `fact_avg_confidence` / `pattern_avg_confidence` / `fact_count` / `pattern_count` 도 함께 읽어 처리 모드 결정에 사용합니다.

총 N개 항목(ProfileFact + DecisionPattern)을 모읍니다.

### 3. 처리 모드 선택 (bulk 분기)

먼저 AskUserQuestion 1회로 처리 방식을 묻습니다 — 사용자가 매일 같은 패턴으로 답하는 케이스를 단축.

**질문 텍스트** (frontmatter 메타 포함):
```
오늘 후보: fact {fact_count}개 (avg {fact_avg_confidence}) · pattern {pattern_count}개 (avg {pattern_avg_confidence})
모두 ledger promotion 통과 (최소 3회 등장 또는 fast path).

어떻게 처리할까요?
```

**옵션** (단일 선택, header "처리 모드"):
- `하나씩 검토` *(추천 — 기본값, 항목별 Yes/No/Edit + No 이유 분류)*
- `batch 선택` — 한 화면에서 여러 항목을 체크박스로 일괄 승인 (체크=Yes, 미체크=dismiss)
- `전부 승인` — 모든 항목을 Yes 로 자동 처리 (vault 일괄 반영, dismissed 호출 없음)
- `전부 No` — 모든 항목을 dismiss 로 자동 처리 (vault 변경 없음, dismissed 누적)

옵션이 5개 이상이면 AskUserQuestion 한계상 두 단계로 분리: 1차 "빠른 처리? (전부 승인/전부 No/중단/세부 검토)" → "세부 검토" 선택 시 2차 "하나씩 검토 / batch 선택". 중단도 항상 사용 가능 (어느 단계에서든 사용자가 "Other" 입력으로 stop 의사 표시 가능).

**모드별 동작**:

#### 모드 A — 하나씩 검토 (default)
N개 항목을 4개씩 묶어 AskUserQuestion 호출. 각 항목은 단일 질문이고 옵션:
- `Yes` — Profile.md / DecisionPatterns.md 에 추가
- `No` — sub-question 으로 dismiss 이유를 물은 뒤 `synapse-memory dismiss-profile --kind {fact|pattern} --text "<원문>" --reason {reason}` 호출 (자세한 흐름은 아래 "No 선택 시 sub-question" 참조)
- `Edit` — 사용자 수정 문구를 별도 AskUserQuestion 으로 받아 그 문구로 추가

질문 텍스트에는 카테고리, 신뢰도, 본문, ledger 메타(있으면)를 모두 포함해 한눈에 판단 가능하게 합니다. **항목은 ledger peak_confidence × seen_count 내림차순으로 정렬해 노출** — 가장 안정 신호부터 묻습니다 (이미 candidate 파일이 정렬되어 있으니 파일 순서 그대로).

##### No 선택 시 sub-question — dismiss 이유 분류
사용자가 한 fact/pattern 에 대해 `No` 를 선택하면 다음 AskUserQuestion 을 1회 추가로 호출합니다 (header `dismiss 이유`).

**질문 텍스트**:
```
"<원문 요약 ~50자>" 를 dismissed 목록에 어떤 이유로 추가할까요?
(이유는 미래 추출 품질 개선과 TTL 차등 적용에 사용됩니다)
```

**옵션** (단일 선택):
- `1회성 작업이라서` → `--reason one_time` (특정 프로젝트/시기에만 한 것)
- `LLM 이 잘못 추출함` → `--reason misclassified` (사실 자체가 틀림)
- `예전엔 맞았지만 지금은 아님` → `--reason user_changed` (성향 변경 — 가장 짧은 TTL 후 다시 물음)
- `애초에 후보 가치 없음` → `--reason irrelevant` (추출 자체가 noise)
- `이유 메모하지 않음` → `--reason ""` (빈 reason 으로 저장)

`other` 옵션은 4개 옵션 한계 때문에 생략. 사용자가 "기타"가 필요하면 위 4개에 안 맞을 때 빈 reason 으로 저장하거나, Bash 로 직접 `--reason other --note "..."` 호출 안내.

선택된 reason 을 그대로 `dismiss-profile --reason <value>` 의 인자로 사용합니다 (한국어 라벨이 아닌 영문 enum 값을 넘김 — 위 매핑표 참조).

사용자가 sub-question 답변을 거부하거나 중단하면 reason 없이 (`--reason ""`) dismiss 호출. dismissed 라인은 그대로 누적되지만 reason 메타는 비게 됩니다.

#### 모드 B — 전부 승인
각 fact 를 Edit 도구로 vault Profile.md 의 해당 카테고리 섹션에 bullet 추가. 각 pattern 을 vault DecisionPatterns.md 의 `## Approved Patterns` 섹션에 `### {trigger}` + 본문으로 추가. dismiss-profile 호출 없음.

확인 1회: "정말 N개 모두 vault 에 추가합니까?" (Yes/No) — Yes 일 때만 실행.

#### 모드 C — 전부 No
각 fact/pattern 에 대해 Bash 로 `synapse-memory dismiss-profile --kind ... --text ...` 호출. vault 는 변경하지 않음. dismissed.jsonl 에만 누적.

확인 1회: "정말 N개 모두 dismiss 합니까? (vault 는 변경 없음)" (Yes/No) — Yes 일 때만 실행. **이 모드는 reason 분류 sub-question 을 생략**하고 빈 reason 으로 저장 — 일괄 처리 단축이 목적이므로 항목별 분류 비용 회피. 항목별 이유를 남기고 싶으면 "하나씩 검토" 모드 사용.

#### 모드 D — 중단
바로 종료. 후보 파일 status 변경 안 함. 결과 요약 단계도 skip.

#### 모드 E — batch 선택 (체크박스 일괄)
fact 와 pattern 을 각각 4개씩 묶어 **multiSelect AskUserQuestion** 으로 노출. 사용자가 vault 에 추가할 것만 체크.

**처리 규칙** (단순화 우선):
- 체크된 항목 → vault Profile.md / DecisionPatterns.md 에 그대로 추가 (Edit 불가 — 본문 수정이 필요하면 "하나씩 검토" 모드 권장)
- 체크 안 한 항목 → 자동 `dismiss-profile --reason ""` 호출 (reason 분류 sub-question 생략 — batch 본질이 일괄 처리)

**fact batch 화면 구성** (한 AskUserQuestion 호출 = 최대 4 questions 묶음, 각 question = 최대 4 옵션 multiSelect):

페이지 수 = ceil(fact_count / 4). 각 페이지 = 1 question, multiSelect=true, 옵션 4개 (마지막 페이지는 4 미만).

각 question 텍스트:
```
다음 fact 중 vault Profile.md 에 추가할 것을 모두 선택 (체크 안 한 것은 자동 dismiss):
```

각 옵션:
- `label`: 본문 첫 30자 (너무 길면 잘림) + ` [conf · ledger 메타]` — 예: `한국어 응답 선호 [0.85 · 6회 등장]`
- `description`: 전체 본문 + ledger 라인 + 카테고리 — 사용자가 hover/focus 로 풀텍스트 확인

**pattern batch 화면**: fact 화면과 동일 로직, 단 vault `DecisionPatterns.md` 의 `## Approved Patterns` 섹션에 `### {trigger}\n\n- 행동: ...\n- 이유: ...` 형태로 추가.

**N 이 페이지당 4 미만**: 마지막 옵션 자리에 `(빈 슬롯)` 더미를 넣지 말고, 그 question 의 options 배열을 실제 항목 개수에 맞게 (최소 2개) 구성. 항목이 단 1개면 batch 모드 의미 없으니 "하나씩 검토" 자동 fallback.

**multi-question 호출**: AskUserQuestion 한 호출에 fact 페이지 + pattern 페이지를 함께 묶을 수 있다면 (총 ≤4 questions) 한 화면에서 양쪽 처리. 5+ questions 되면 분할.

**예시 호출** (fact 7개 + pattern 2개):
```
AskUserQuestion(questions=[
  {question: "fact 1-4 중 vault 추가할 것 선택", multiSelect: true, options: [fact1, fact2, fact3, fact4]},
  {question: "fact 5-7 중 vault 추가할 것 선택", multiSelect: true, options: [fact5, fact6, fact7]},
  {question: "pattern 1-2 중 vault 추가할 것 선택", multiSelect: true, options: [pat1, pat2]},
])  # 3 questions, 한 호출로 끝
```

**선택 결과 처리** (모든 question 의 answers 모은 뒤 일괄 처리):
1. 체크된 fact 각각: Edit 도구로 vault Profile.md 의 해당 카테고리 섹션 끝에 bullet 추가
2. 체크된 pattern 각각: Edit 도구로 vault DecisionPatterns.md 의 `## Approved Patterns` 섹션에 추가
3. 체크 안 한 fact: Bash 로 `synapse-memory dismiss-profile --kind fact --text "<원문>"` (reason 미지정)
4. 체크 안 한 pattern: Bash 로 `synapse-memory dismiss-profile --kind pattern --text "<trigger>"` (reason 미지정)

**제약**:
- batch 에서는 Edit 옵션 없음 (multiSelect 와 양립 불가). 본문 수정이 필요하면 사용자가 batch 처리 후 vault 에서 직접 편집하거나, "하나씩 검토" 재실행.
- batch 에서는 reason 분류 없음 (전부 No 와 동일). reason 메모가 필요한 항목은 batch 끝낸 뒤 사용자가 직접 `dismiss-profile --kind ... --reason ...` 으로 라인 추가 (단, 이미 reason="" 로 dismissed 되어 있으면 멱등 — 두 번째 호출이 무시됨; 이 경우 `_dismissed.jsonl` 에서 해당 라인 reason 필드를 직접 수정).

### 4. 승인분 반영

- ProfileFact `Yes` (또는 Edit 결과): vault `Profile.md`의 해당 카테고리 섹션(예: `## Tech / Domain`) 끝에 bullet으로 Edit 도구로 추가
- DecisionPattern `Yes` (또는 Edit 결과): vault `DecisionPatterns.md`의 `## Approved Patterns` 섹션에 `### {trigger}` + 본문 추가
- `No`: Bash 도구로 `synapse-memory dismiss-profile --kind fact --text "<원문>"` (DecisionPattern 이면 `--kind pattern --text "<trigger>"`) 호출 → dismissed 목록에 누적되어 다음 daily 부터 동일 항목 재추출 차단 (기본 TTL 90일 후 자동 해제)

vault Profile/Patterns 경로는 CLAUDE.md의 `90_System/AI/Profile.md`, `90_System/AI/DecisionPatterns.md` 기본값을 사용하거나, 사용자에게 위치를 묻습니다.

dismissed 목록은 `90_System/AI/MemoryInbox/_dismissed.jsonl` 에 한 줄씩 누적됩니다. 사용자 성향이 바뀌어 다시 후보로 보고 싶으면 해당 라인을 직접 삭제(또는 `dismissed_at` 날짜를 과거로 더 끌어내려 TTL 만료시킴)하면 다음 daily 에서 자동 재노출됩니다.

### 5. 후보 파일 마감

승인 단계가 끝나면 후보 파일 frontmatter를 Edit 도구로 갱신합니다.

```diff
-status: pending_review
+status: applied
+applied_date: <오늘 ISO 날짜>
```

### 6. 결과 요약

처리 완료 후 다음을 출력합니다.

- 처리 모드 (하나씩 / batch 선택 / 전부 승인 / 전부 No / 중단)
- 총 N개 중 ✅ approved / ✏️ edited / ❌ dismissed 개수 (batch 모드는 edited=0)
- 반영된 카테고리·패턴 목록 (있으면)
- 마감된 후보 파일 경로

`--all-pending`이면 다음 날짜의 후보로 이어집니다. 단 **중단 모드**가 선택되면 `--all-pending` 도 거기서 멈춥니다 (사용자 의도 존중).

## 주의

- AskUserQuestion은 한 번에 최대 4 questions/call이므로 N>4면 자동 분할.
- batch 모드 (E) 는 한 question 에 최대 4 options multiSelect 이므로 fact/pattern 합쳐 페이지 수가 4 questions 를 초과하면 여러 호출로 분할.
- 사용자가 중간에 중단하면 처리된 항목까지는 보존하되 후보 파일은 그대로 pending_review로 둘 것 (idempotent — 다시 호출하면 처음부터).
- batch 모드는 Edit 옵션과 reason 분류를 생략 — 단순화 우선. 본문 수정/reason 분류가 필요하면 "하나씩 검토" 모드 사용.
- vault Profile.md / DecisionPatterns.md가 없으면 사용자에게 알리고 신규 생성 동의를 받음.
