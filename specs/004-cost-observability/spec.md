# Feature Specification: Cost Observability

**Feature Branch**: `004-cost-observability`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "FR-A3/A4: 모든 Claude/apfel 호출의 비용·토큰·elapsed 를 cost.jsonl 에 append-only 기록하고, synapse-memory cost summary 로 최근 N일 비용을 command/model 기준으로 집계한다."

부모 plan: `specs/001-roadmap/plan.md` (FR-A3, FR-A4), roadmap spec `specs/001-roadmap/spec.md` v0.5 P1.

## User Scenarios & Testing *(mandatory)*

이 feature 의 사용자는 Synapse Memory 를 매일 쓰는 단일 소유자다. 목표는 AI 호출 비용이 보이지 않는 상태를 없애고, daily/report/resume 기능이 사용할 수 있는 로컬 비용 원장을 만드는 것이다.

### User Story 1 - AI 호출 비용 자동 기록 (Priority: P1)

사용자는 `ask`, `me`, `daily` 같은 명령이 내부적으로 Claude Code CLI 또는 apfel 을 호출한 뒤, 호출별 토큰·비용·elapsed 가 로컬 private cost log 에 자동으로 남기를 기대한다.

**Why this priority**: v0.5 의 "쓰면 더 똑똑해지는 도구"는 비용이 추적되어야 매일 실행 가능한 도구가 된다. 자동 기록이 없으면 summary 와 daily report 는 신뢰할 입력을 가질 수 없다.

**Independent Test**: 외부 CLI 를 mock 한 상태에서 AI 호출 경로를 1회 실행하면 `~/.synapse/private/cost.jsonl` 에 command, provider, model, input/output token, usd, elapsed_s 를 포함한 유효 JSON 1줄이 append 된다.

**Acceptance Scenarios**:

1. **Given** `ask` 가 Claude Code CLI 를 통해 답변을 생성한다, **When** 호출이 성공적으로 종료된다, **Then** cost log 에 해당 command 와 model, token, usd, elapsed_s 가 1줄 기록된다.
2. **Given** apfel redaction 또는 local model helper 호출이 실행된다, **When** 호출이 종료된다, **Then** cost log 에 provider 가 구분된 1줄이 기록된다.
3. **Given** 외부 호출이 실패한다, **When** 명령이 오류를 반환한다, **Then** 실패 여부와 elapsed_s 를 포함한 cost event 가 기록되어 비용·장애 추적에서 누락되지 않는다.

---

### User Story 2 - 최근 비용 요약 보기 (Priority: P2)

사용자는 최근 N일 동안 어떤 command 또는 model 이 비용을 가장 많이 썼는지 CLI 에서 즉시 확인할 수 있다.

**Why this priority**: 자동 기록이 쌓여도 집계가 없으면 사용자는 비용을 의사결정에 쓰기 어렵다. summary 는 daily report 이전에 단독으로 가치가 있다.

**Independent Test**: 여러 날짜와 command/model 을 가진 cost log 를 준비한 뒤 `synapse-memory cost summary --days 30 --by command` 를 실행하면 기간 내 row 만 command 별로 합산되어 출력된다.

**Acceptance Scenarios**:

1. **Given** 최근 30일 cost event 가 여러 command 에 존재한다, **When** `cost summary --by command` 를 실행한다, **Then** command 별 호출 수, token 합계, usd 합계, elapsed 합계가 표시된다.
2. **Given** 같은 로그가 존재한다, **When** `cost summary --by model --json` 을 실행한다, **Then** model 별 집계가 기계가 읽을 수 있는 JSON 으로 출력된다.
3. **Given** cost log 가 없거나 기간 내 event 가 없다, **When** summary 를 실행한다, **Then** "데이터 없음" 안내를 출력하고 exit 0 으로 종료한다.

---

### User Story 3 - 비용 로그를 안전하게 운영하기 (Priority: P3)

사용자는 비용 로그가 손상되거나 오래 쌓여도 daily pipeline 을 깨뜨리지 않고, 민감한 prompt 원문이 cost log 에 남지 않기를 기대한다.

**Why this priority**: 비용 로그는 매 호출마다 쓰이는 기반 파일이다. 손상·권한·민감정보 정책이 약하면 observability 가 오히려 장애 원인이 된다.

**Independent Test**: 손상된 cost.jsonl tail 을 준비한 뒤 새 event 기록 또는 summary 를 실행하면 정상 prefix 는 보존되고 손상 구간은 backup 으로 분리되며, prompt/body 원문은 기록되지 않는다.

**Acceptance Scenarios**:

1. **Given** cost log tail 에 유효하지 않은 JSON 줄이 있다, **When** 새 cost event 를 기록한다, **Then** 정상 row 는 보존되고 손상 tail 은 backup 된 뒤 새 row 가 기록된다.
2. **Given** AI prompt 에 개인정보가 포함되어 있다, **When** cost event 가 기록된다, **Then** cost log 는 prompt/body 원문을 저장하지 않고 token/cost metadata 만 저장한다.
3. **Given** cost log 디렉터리가 없다, **When** 첫 event 를 기록한다, **Then** private directory 가 생성되고 사용자 전용 권한으로 파일이 생성된다.

### Edge Cases

- cost event 의 token 수를 provider 가 제공하지 않는 경우 `input_tokens`/`output_tokens` 는 null 또는 0 으로 기록하되 summary 에서 안전하게 처리한다.
- usd 산정이 불가능한 provider 또는 local-only 호출은 `usd=0` 과 `pricing_source="unpriced"` 로 기록한다.
- 호출이 timeout 또는 non-zero exit 으로 끝나도 elapsed_s 와 status 를 남긴다.
- cost.jsonl 이 없으면 summary 는 오류가 아니라 "데이터 없음"으로 끝난다.
- `--days 0` 또는 음수는 validation error 로 처리한다.
- `--by` 는 `command` 또는 `model` 만 허용한다.
- JSON 출력은 사람이 읽는 표 헤더를 섞지 않는다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST append one private cost event after every Claude Code CLI call that reaches the external process boundary.
- **FR-002**: System MUST append one private cost event after every apfel call that reaches the external process boundary.
- **FR-003**: Each cost event MUST include timestamp, command, provider, model, input_tokens, output_tokens, usd, elapsed_s, and status.
- **FR-004**: Cost events MUST NOT include raw prompts, raw responses, card bodies, file contents, or feedback reasons.
- **FR-005**: System MUST write cost events to `~/.synapse/private/cost.jsonl` as append-only JSON Lines.
- **FR-006**: System MUST create the private directory and cost log with user-only permissions when missing.
- **FR-007**: System MUST preserve readable cost events and back up unreadable tail content before accepting new writes to a damaged log.
- **FR-008**: System MUST keep command success/failure behavior unchanged when cost logging fails, while surfacing a warning that the cost event was not recorded.
- **FR-009**: System MUST provide `synapse-memory cost summary [--days N] [--by command|model] [--json]`.
- **FR-010**: `cost summary` MUST default to `--days 30` and `--by command`.
- **FR-011**: `cost summary` MUST filter events by timestamp within the requested lookback window.
- **FR-012**: `cost summary` MUST aggregate call count, total input_tokens, total output_tokens, total usd, and total elapsed_s for each group.
- **FR-013**: `cost summary --json` MUST output valid JSON with no human table decoration.
- **FR-014**: `cost summary` MUST exit 0 with actionable "데이터 없음" output when the log is absent or no events match the window.
- **FR-015**: System MUST be testable without real apfel, Claude Code CLI, or network access by using mocked provider outputs.

### Key Entities *(include if feature involves data)*

- **CostEvent**: A single external AI/helper call record. Key attributes: timestamp, command, provider, model, token counts, usd, elapsed_s, status, optional error_kind.
- **CostSummaryGroup**: A derived aggregate for one command or model. Key attributes: group key, calls, total tokens, total usd, total elapsed_s, first_seen, last_seen.
- **PricingRule**: A local deterministic rule for converting provider/model token counts to USD when pricing is known; otherwise marks the event unpriced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 mocked Claude/apfel calls produce 100 valid cost.jsonl rows in chronological append order.
- **SC-002**: A cost event never persists raw prompt or response text in golden tests that include personal data markers.
- **SC-003**: `cost summary --days 30 --by command` returns correct group totals for a mixed fixture with at least 3 commands and 2 models.
- **SC-004**: `cost summary --json` output parses as JSON and contains no table-only strings.
- **SC-005**: Missing or empty cost log exits 0 and prints "데이터 없음".
- **SC-006**: Cost logging adds less than 20 ms overhead per mocked event append on the local machine.
- **SC-007**: Damaged log recovery preserves all readable prefix events and backs up unreadable tail content before appending.

## Assumptions

- The tool remains single-user and local-first.
- Cost observability covers external Claude Code CLI and apfel process calls in this feature. Pure in-process deterministic functions are out of scope.
- USD pricing is best-effort and deterministic. Unknown or local-only models are allowed to record `usd=0` with an explicit unpriced marker.
- `daily` report generation will consume `cost.jsonl` in a later feature; this feature only creates the log and CLI summary.
- Existing command output should not become noisy; cost logging warnings should appear only on logging failure.
- The feature does not introduce telemetry, network reporting, or remote cost upload.
