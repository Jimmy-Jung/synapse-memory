# Feature Specification: /sm:apply-profile — GUI 승인 워크플로 + /sm:daily 자동 연결

**Feature Branch**: `0.12.0/feature/014-apply-profile`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "daily스킬 사용시 plan mode로 변경해서 어떤 데이터를 profile에 적용할껀지 워크플로우 추가 필요"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Profile 후보 항목별 GUI 승인 (Priority: P1)

`/sm:apply-profile [date]` 슬래시를 호출하면 그 날짜의 MemoryInbox candidate를 자동으로 읽고, ProfileFact·DecisionPattern 항목을 4개씩 묶어 AskUserQuestion으로 Y/N/Edit를 받는다. 사용자가 승인한 항목만 `Profile.md`·`DecisionPatterns.md`에 반영되고, MemoryInbox 후보 파일의 frontmatter는 `status: applied` + `applied_date`로 마감된다.

**Why this priority**: 사용자가 방금 직접 경험한 마찰을 도구로 끌어올림. plan-mode GUI 선호 + 항목별 정확성을 위한 질문 환영이라는 사용자 패턴 직접 반영.

**Independent Test**: 합성 `Profile-2026-05-17.md` 후보 파일 + 빈 Profile.md/DecisionPatterns.md를 임시 vault에 두고 슬래시 흐름을 시뮬레이션 (AskUserQuestion 응답 mock) → 승인분만 반영, MemoryInbox 파일 frontmatter `applied`.

**Acceptance Scenarios**:

1. **Given** `MemoryInbox/{YYYY}/{MM}/Profile-2026-05-17.md` 후보 파일 + Profile.md/DecisionPatterns.md 존재, **When** 사용자가 `/sm:apply-profile 2026-05-17` 호출, **Then** 슬래시 prompt가 항목 파싱 → AskUserQuestion 흐름 → 사용자가 Yes 답한 항목이 Profile.md에 Edit으로 추가됨
2. **Given** 후보 파일 frontmatter `status: pending_review`, **When** apply 완료 후, **Then** frontmatter가 `status: applied` + `applied_date: 2026-05-17` 로 변경
3. **Given** date 인자 미지정, **When** `/sm:apply-profile` 호출, **Then** 오늘 날짜의 후보를 찾아 처리
4. **Given** 해당 날짜의 후보 파일 없음, **When** 호출, **Then** 안내 메시지 + 사용 가능한 날짜 목록 출력 후 종료
5. **Given** 후보 파일 `status: applied`로 이미 마감, **When** 다시 호출, **Then** "이미 적용됨" 안내 + 재처리 확인 (또는 idempotent: 이미 적용된 항목은 skip)

---

### User Story 2 - /sm:daily 종료 후 apply 흐름으로 자동 연결 (Priority: P1)

`/sm:daily` 실행이 정상 종료(`update_profile` 단계 성공으로 신규 후보 파일 생성)되면 슬래시 prompt가 자동으로 apply 흐름으로 이어진다. 사용자가 일일 사용 시 매번 `/sm:apply-profile`를 따로 입력할 필요 없음.

**Why this priority**: 사용자 매일 호출 흐름의 마찰 직접 해소. `/sm:daily` 후 후보가 쌓이는 것 자체가 핵심 가치.

**Independent Test**: `/sm:daily --quick` 실행 후 신규 Profile candidate가 생성됐을 때 슬래시 prompt가 즉시 apply 안내를 출력하는지 (수동 검증).

**Acceptance Scenarios**:

1. **Given** `/sm:daily` 정상 종료 + 신규 `Profile-YYYY-MM-DD.md` 생성, **When** prompt 흐름, **Then** 자동으로 "Profile 후보를 검토할까요?" 안내 + apply-profile 흐름 진입 옵션 제공
2. **Given** `/sm:daily --dry-run`, **When** 종료, **Then** apply 흐름 자동 진입 안 함 (dry-run은 후보 생성하지 않음)
3. **Given** `update_profile` 단계 실패 또는 skip, **When** daily 종료, **Then** apply 흐름 자동 진입 안 함

---

### User Story 3 - 과거 날짜 일괄 처리 (Priority: P2)

여러 날짜에 걸쳐 쌓인 MemoryInbox 후보들을 한 번에 처리하고 싶을 때 `/sm:apply-profile --all-pending` (또는 동등) 옵션으로 status가 pending_review인 모든 후보를 순차 처리한다.

**Why this priority**: 매일 사용 안 하던 사용자가 한 번에 묶어 처리하는 시나리오. P2 — MVP는 아니지만 자연스러운 확장.

**Independent Test**: 3개 날짜의 pending 후보를 두고 `--all-pending` 호출 → 3 cycle 순차 처리, 각 후보 마감.

**Acceptance Scenarios**:

1. **Given** 3개 날짜의 pending 후보, **When** `/sm:apply-profile --all-pending`, **Then** 오래된 날짜부터 순차 처리, 각 사이클 사용자가 항목별 승인
2. **Given** 사용자가 중간에 중단, **When** 종료, **Then** 그때까지 처리된 날짜만 `applied`, 나머지는 그대로 pending

### Edge Cases

- 후보 파일의 ProfileFact 카테고리가 미정의 (`interest` 외 다른 라벨) → AI prompt가 그대로 사용자에게 보여줌, 사용자가 결정
- 사용자가 "Edit" 선택 → AI가 새 텍스트 입력 받아 그 문장만 Profile.md에 반영
- 한 번에 28개 같이 큰 후보 → 4개씩 자동 분할 (AskUserQuestion 최대 4 questions/call 제약)
- Profile.md / DecisionPatterns.md 미존재 → AI가 안내 후 사용자 결정 (신규 생성 vs 중단)
- MemoryInbox 후보 파일이 `_legacy/` 폴더 안 → recursive 검색 또는 안내 (folders.find_candidate_files 재사용)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `/sm:apply-profile [date]` slash command (Claude Code marketplace)
- **FR-002**: Slash prompt MUST instruct AI to:
  1. Resolve target file: `MemoryInbox/{YYYY}/{MM}/Profile-{date}.md` (날짜 인자 없으면 오늘 또는 가장 최근 pending)
  2. Parse `## ProfileFact 후보` / `## DecisionPattern 후보` 섹션을 항목으로 분리
  3. 4개씩 묶어 AskUserQuestion (Yes / No / Edit 옵션)
  4. 승인분만 `Profile.md` (해당 카테고리 섹션) 또는 `DecisionPatterns.md` (`## Approved Patterns`)에 Edit으로 추가
  5. MemoryInbox 후보 파일 frontmatter `status: pending_review` → `status: applied` + `applied_date: YYYY-MM-DD` 추가
- **FR-003**: 사용자가 "Edit" 선택 시 AI가 별도 AskUserQuestion으로 수정 문구 입력 받음
- **FR-004**: `commands/daily.md` 슬래시 prompt가 update_profile 성공 시 apply 흐름을 즉시 제안 (사용자가 yes 답해야 진입)
- **FR-005**: `synapse-memory list-pending-profiles` CLI 보조 명령 — 모든 pending 후보 날짜 + 경로 출력 (date 인자 미지정 시 슬래시가 후보 발견에 사용)
- **FR-006**: 슬래시 호출 + `--all-pending` 모드 — list-pending 결과 모든 날짜를 오래된 순으로 처리
- **FR-007**: `applied` 된 후보 파일은 list-pending 결과에 포함 안 됨
- **FR-008**: System MUST NOT auto-trigger apply without user confirmation (Constitution VI Installation Consent)

### Key Entities

- **MemoryInbox candidate**: `Profile-{ISO date}.md` 파일. frontmatter `status: pending_review | applied`. 본문 `## ProfileFact 후보` / `## DecisionPattern 후보` 섹션의 bullet 라인.
- **Profile target**: vault `Profile.md` (카테고리별 섹션) / `DecisionPatterns.md` (`## Approved Patterns` 섹션).
- **Slash prompt 흐름**: AskUserQuestion 4개씩 묶어 항목별 Y/N/Edit. AI가 Edit 시 별도 질문으로 수정 문구 받음.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `synapse-memory list-pending-profiles` 호출 → recursive scan으로 모든 pending 후보 경로 출력 (회귀 테스트)
- **SC-002**: 합성 후보 파일에서 ProfileFact·DecisionPattern 파싱 정확도 100% (회귀 테스트)
- **SC-003**: 한 번 apply 완료된 후보가 다시 list-pending에 안 나옴 (idempotent)
- **SC-004**: 신규 + 회귀 테스트 통과 (`pytest` 876 + 신규 ≥ 6 = 882+)

## Assumptions

- 사용자는 `/sm:daily` → `/sm:apply-profile` 흐름을 의식적으로 사용한다 (자동 강제 없음, FR-008)
- AskUserQuestion 4개/call 제약은 슬래시 prompt가 자동 분할로 처리 — CLI 코드 변경 없음
- ProfileFact/DecisionPattern 파싱은 AI가 markdown 읽고 직접 처리 (정규 파서 코드 신설 안 함). CLI 보조는 list-pending만.
- vault `Profile.md` / `DecisionPatterns.md` 신규 생성은 본 sprint 범위 아님 (이미 vault에 있다고 가정)
- 011 sprint 결과로 MemoryInbox는 `{YYYY}/{MM}/` 하위 구조. recursive scan 필요 — `folders.find_candidate_files` 재사용.
