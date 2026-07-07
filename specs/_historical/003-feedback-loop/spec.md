# Feature Specification: Feedback Loop

**Feature Branch**: `003-feedback-loop`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "사용자가 ask/me 답변, 특정 card, decision pattern 에 accept/reject/weight 피드백을 남기고, feedback.jsonl 에 append-only 기록하며 다음 인덱싱에서 카드 검색 가중치에 반영한다."

## User Scenarios & Testing *(mandatory)*

이 feature 의 사용자는 Synapse Memory 를 매일 쓰는 단일 소유자다. 목표는 AI 답변이 틀렸거나 유용했을 때 즉시 신호를 남기고, 그 신호가 다음 검색·회상 품질에 누적되도록 만드는 것이다.

### User Story 1 - 직전 답변에 피드백 남기기 (Priority: P1)

사용자는 `ask`, `me what-did-i-think`, `me decide` 답변 직후 그 답변이 유용했는지 또는 관련 없는 출처를 사용했는지 빠르게 남길 수 있다.

**Why this priority**: 직전 답변 피드백은 가장 낮은 마찰로 남길 수 있는 학습 신호다. v0.5 의 "쓰면 더 똑똑해지는 도구" 가치를 단독으로 입증한다.

**Independent Test**: 직전 답변이 인용 출처를 가진 상태에서 `synapse-memory feedback last --reject "<이유>"` 를 실행하면 피드백 이벤트 1건이 기록되고, stdout 이 어떤 대상에 어떤 신호가 남았는지 알려준다.

**Acceptance Scenarios**:

1. **Given** 직전 `ask` 답변이 카드 2개를 인용했다, **When** 사용자가 `feedback last --reject "관련 없음"` 을 실행한다, **Then** 직전 답변과 인용 카드 맥락을 참조하는 reject 이벤트가 1건 기록된다.
2. **Given** 직전 `me what-did-i-think` 답변이 만족스럽다, **When** 사용자가 `feedback last --accept` 를 실행한다, **Then** accept 이벤트가 1건 기록되고 다음 인덱싱에서 긍정 신호로 해석될 수 있다.
3. **Given** 직전 답변 기록이 없다, **When** 사용자가 `feedback last --reject "틀림"` 을 실행한다, **Then** 시스템은 기록할 대상이 없다는 actionable 안내를 출력하고 피드백 로그를 변경하지 않는다.

---

### User Story 2 - 특정 카드나 패턴에 직접 가중치 조정하기 (Priority: P2)

사용자는 답변 직후가 아니더라도 특정 카드나 decision pattern 이 자주 잘못 쓰인다고 판단하면 직접 accept/reject 또는 weight 조정을 남길 수 있다.

**Why this priority**: 직전 답변 외에도 사용자가 이미 알고 있는 품질 문제를 바로 교정할 수 있어야 장기적으로 검색 결과가 안정된다.

**Independent Test**: 존재하는 card id 또는 pattern id 를 대상으로 `feedback card <id> --reject "<이유>"`, `feedback pattern <id> --weight -0.3` 을 실행하면 대상별 이벤트가 구분되어 기록된다.

**Acceptance Scenarios**:

1. **Given** 사용자가 특정 ProjectCard 가 특정 주제에 부적합하다고 안다, **When** `feedback card <card_id> --reject "<이유>"` 를 실행한다, **Then** 해당 card 를 대상으로 하는 reject 이벤트가 기록된다.
2. **Given** 사용자가 특정 decision pattern 의 영향력을 낮추고 싶다, **When** `feedback pattern <pattern_id> --weight -0.3` 을 실행한다, **Then** 해당 pattern 을 대상으로 하는 weight 이벤트가 기록된다.
3. **Given** 사용자가 `--accept`, `--reject`, `--weight` 를 동시에 지정한다, **When** 명령을 실행한다, **Then** 시스템은 하나의 action 만 허용한다는 오류를 출력하고 기록하지 않는다.

---

### User Story 3 - 다음 검색 품질에 피드백 반영하기 (Priority: P3)

사용자는 누적 피드백이 단순 로그에 머물지 않고 다음 인덱싱과 검색 결과에 영향을 준다는 것을 확인할 수 있다.

**Why this priority**: 피드백 루프는 기록 자체보다 이후 회상과 추천 품질을 바꾸는 것이 핵심 가치다. 다만 P1/P2 의 입력 경로가 먼저 존재해야 검증 가능하다.

**Independent Test**: 같은 card 에 reject 이벤트를 남긴 뒤 다음 인덱싱을 실행하면 해당 card 의 검색 가중치가 기본값보다 낮아졌음을 확인할 수 있다.

**Acceptance Scenarios**:

1. **Given** 특정 card 에 reject 이벤트가 1건 기록되어 있다, **When** 다음 인덱싱이 실행된다, **Then** 해당 card 의 검색 가중치는 기본값보다 낮게 반영된다.
2. **Given** 특정 card 에 accept 이벤트가 1건 기록되어 있다, **When** 다음 인덱싱이 실행된다, **Then** 해당 card 의 검색 가중치는 기본값보다 높게 반영된다.
3. **Given** 한 card 에 상충하는 accept/reject 이벤트가 여러 건 있다, **When** 다음 인덱싱이 실행된다, **Then** 시스템은 모든 이벤트를 시간순으로 집계하고 허용 범위 안의 최종 가중치를 산출한다.

### Edge Cases

- 직전 답변 참조 파일이 없거나 손상된 경우 피드백 기록 없이 복구 안내를 출력한다.
- 피드백 로그에 손상된 줄이 있으면 정상 줄은 보존하고 손상 구간은 백업한 뒤 새 이벤트 기록을 계속할 수 있어야 한다.
- reject 이유가 비어 있으면 사용자에게 이유 입력이 필요하다고 안내하고 기록하지 않는다.
- 이유 텍스트에 개인정보나 민감정보가 포함될 수 있으므로 저장 전 안전한 텍스트만 남아야 한다.
- 알 수 없는 card id 또는 pattern id 는 기록 전에 사용자에게 대상 확인 실패를 알려야 한다.
- 가중치가 허용 범위를 벗어나면 기록하지 않고 허용 범위를 안내한다.
- 피드백 이벤트 기록 중 파일 권한 문제가 발생하면 부분 기록을 남기지 않고 오류를 반환한다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `synapse-memory feedback last` for recording feedback against the most recent AI answer.
- **FR-002**: System MUST support `accept`, `reject`, and explicit `weight` feedback actions, with exactly one action per event.
- **FR-003**: System MUST require a non-empty reason for reject feedback.
- **FR-004**: System MUST record feedback as append-only private events containing event id, timestamp, target kind, target reference, action, weight, optional reason, and answer context when available.
- **FR-005**: System MUST keep enough metadata from AI answers for `feedback last` to resolve the answer and its cited targets.
- **FR-006**: System MUST support direct card feedback by stable card id.
- **FR-007**: System MUST support direct decision pattern feedback by stable pattern id.
- **FR-008**: System MUST validate target existence before recording direct card or pattern feedback.
- **FR-009**: System MUST sanitize or redact free-text feedback reasons before persistent storage.
- **FR-010**: System MUST avoid sending feedback commands or feedback reasons to an external LLM.
- **FR-011**: System MUST provide clear stdout confirmation that names the target, action, weight effect, and next application point.
- **FR-012**: System MUST leave no partial event when validation, redaction, or file write fails.
- **FR-013**: System MUST recover from a damaged feedback log by preserving readable events and backing up unreadable content before accepting new writes.
- **FR-014**: System MUST aggregate card feedback into a bounded search weighting signal for the next indexing or retrieval cycle.
- **FR-015**: System MUST keep direct card content unchanged when feedback is recorded; feedback changes retrieval weighting only.
- **FR-016**: System MUST provide actionable no-op output when `feedback last` has no recent answer context.
- **FR-017**: System MUST be testable without apfel, Claude Code CLI, or network access.

### Key Entities *(include if feature involves data)*

- **FeedbackEvent**: A single user signal about an answer, card, or pattern. Key attributes: event id, timestamp, target kind, target reference, action, weight, reason, answer context.
- **LastAnswerReference**: The latest AI answer context used by `feedback last`. Key attributes: answer id, command family, citations, timestamp, optional session id.
- **FeedbackTarget**: The object receiving feedback. It can be an answer, card, or decision pattern and must have a stable reference.
- **FeedbackAggregate**: The derived per-target score calculated from one or more FeedbackEvents. It is used to influence future ranking without mutating the original card body.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can record feedback for the most recent answer in under 10 seconds from reading the answer.
- **SC-002**: 100 consecutive feedback events are recorded without losing event order or producing invalid event records.
- **SC-003**: When a card receives one reject event, the next indexing or retrieval cycle shows a measurable score decrease for that card.
- **SC-004**: When a card receives one accept event, the next indexing or retrieval cycle shows a measurable score increase for that card.
- **SC-005**: If no recent answer context exists, the command exits without changing the feedback log and explains the next valid action.
- **SC-006**: Free-text reasons containing golden-set personal data do not persist the original sensitive tokens after sanitization.
- **SC-007**: Feedback commands complete without requiring external AI tools or network access.

## Assumptions

- The tool remains single-user and local-first.
- `ask`, `me what-did-i-think`, and `me decide` are the answer-producing commands that need last-answer tracking for this feature.
- Reject defaults to a negative signal and accept defaults to a positive signal; explicit weight is reserved for advanced adjustment.
- Feedback events are permanent audit records. Later corrections are represented by new events rather than editing previous events.
- Decision outcome learning for v0.8 is out of scope except for recording pattern-directed feedback in a compatible shape.
- This feature does not add a UI beyond the CLI and slash-command documentation surface.
