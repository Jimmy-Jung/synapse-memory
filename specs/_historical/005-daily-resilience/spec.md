# Feature Specification: Daily Resilience

**Feature Branch**: `005-daily-resilience`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "daily pipeline stage dependency, skip/resume, GitHub Actions CI for pytest ruff mypy"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 실패 단계와 의존 단계가 명확히 보이는 daily 실행 (Priority: P1)

사용자는 `daily`를 unattended로 실행했을 때 어떤 stage가 성공했고, 어떤 stage가 실패했으며, 어떤 downstream stage가 의존성 때문에 SKIP 되었는지 한눈에 확인할 수 있어야 한다.

**Why this priority**: daily는 Synapse Memory의 장기 운영 진실원본을 만드는 배치 파이프라인이다. 실패가 뭉뚱그려지면 사용자가 재실행 범위를 판단할 수 없고, 자동화 신뢰도도 떨어진다.

**Independent Test**: classify stage를 강제로 실패시키는 테스트 실행만으로 `collect=success`, `cluster=success`, `classify=failed`, `generate/index/profile=skipped` 상태와 exit code 1을 검증할 수 있다.

**Acceptance Scenarios**:

1. **Given** 모든 stage가 성공한다, **When** 사용자가 `synapse-memory daily`를 실행한다, **Then** 모든 stage가 `success`로 기록되고 종료 코드는 0이다.
2. **Given** classify stage가 실패한다, **When** 사용자가 `synapse-memory daily`를 실행한다, **Then** classify는 `failed`, classify에 의존하는 stage는 `skipped`, 독립 stage는 실행 결과를 보존하고 종료 코드는 1이다.
3. **Given** 특정 stage가 skipped 된다, **When** daily summary가 출력된다, **Then** skip reason에는 어떤 upstream stage 때문에 건너뛰었는지 포함된다.

---

### User Story 2 - 실패 지점부터 안전하게 재개하기 (Priority: P2)

사용자는 `daily --resume-from <stage>`로 실패한 단계부터 재시도할 수 있어야 하며, 앞선 stage를 불필요하게 다시 실행하지 않아야 한다.

**Why this priority**: daily 단계 중 일부는 외부 도구나 로컬 모델 상태에 영향을 받는다. 전체 재실행만 가능하면 시간이 길어지고 idempotence 확인이 어려워진다.

**Independent Test**: `daily --resume-from classify`를 실행했을 때 collect/cluster가 `skipped(resume-before-target)`로 표시되고 classify 이후 stage만 실행되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 전날 daily에서 classify가 실패했다, **When** 사용자가 `synapse-memory daily --resume-from classify`를 실행한다, **Then** classify부터 마지막 stage까지 순서대로 실행된다.
2. **Given** 사용자가 존재하지 않는 stage 이름을 입력한다, **When** `daily --resume-from nope`를 실행한다, **Then** 명확한 오류 메시지와 exit code 2가 반환되고 어떤 stage도 실행되지 않는다.
3. **Given** 사용자가 중간 stage부터 재개한다, **When** summary가 출력된다, **Then** target 이전 stage는 skipped로 표시되어 재개 범위가 드러난다.

---

### User Story 3 - PR마다 자동 검증되는 CI (Priority: P3)

사용자는 main과 PR에서 pytest, ruff, mypy가 자동으로 실행되어 daily 회귀가 머지 전에 차단된다는 신뢰를 얻어야 한다.

**Why this priority**: local 검증만으로는 장기 운영 안정성을 담보할 수 없다. v0.5의 daily resilience는 CI green을 머지 조건으로 삼아야 한다.

**Independent Test**: GitHub Actions workflow 파일을 확인하고, apfel/Claude/Codex CLI가 없는 환경에서도 mock 기반 테스트가 통과하는 명령 구성이 존재하는지 검증한다.

**Acceptance Scenarios**:

1. **Given** PR이 열렸다, **When** GitHub Actions가 실행된다, **Then** pytest, ruff, mypy job이 실행된다.
2. **Given** CI 환경에 apfel/Claude/Codex CLI가 없다, **When** workflow가 실행된다, **Then** mock 기반 테스트만으로 통과 가능해야 한다.
3. **Given** pytest 또는 ruff 또는 mypy가 실패한다, **When** workflow가 완료된다, **Then** PR check가 실패로 표시된다.

### Edge Cases

- `--resume-from`이 첫 stage를 가리키면 일반 `daily`와 동일한 stage 범위를 실행한다.
- `--resume-from`이 마지막 stage를 가리키면 마지막 stage만 실행하고 이전 stage는 resume skip으로 표시한다.
- upstream 실패가 여러 downstream stage에 영향을 주면 각 skipped stage가 동일한 upstream failure를 reason으로 가진다.
- stage가 실패한 뒤에도 summary와 DailyReport 생성은 가능한 범위에서 계속되어야 한다.
- DailyReport 저장 자체가 실패해도 원래 stage 실패 원인을 덮어쓰지 않아야 한다.
- CI workflow는 secrets나 실제 개인 vault 경로에 의존하지 않아야 한다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define the daily pipeline as an ordered list of named stages with explicit dependency metadata.
- **FR-002**: System MUST record each stage result as `success`, `failed`, or `skipped` with elapsed time and a one-line summary.
- **FR-003**: System MUST skip stages whose required upstream stage failed and include the upstream stage name in the skip reason.
- **FR-004**: System MUST return exit code 1 when any stage fails, even if downstream skips are handled cleanly.
- **FR-005**: System MUST return exit code 0 only when all selected executable stages complete successfully.
- **FR-006**: Users MUST be able to run `synapse-memory daily --resume-from <stage>` to start execution at a named stage.
- **FR-007**: System MUST reject unknown `--resume-from` stage names before any stage executes and return exit code 2.
- **FR-008**: System MUST mark stages before the resume target as skipped with a resume-specific reason in the run summary.
- **FR-009**: System MUST generate a DailyReport markdown file after daily execution with stage status, elapsed time, counters, skipped reasons, failures, new Card count, profile fact count, and estimated USD when available.
- **FR-010**: System MUST preserve the original stage failure as the primary failure if DailyReport generation fails.
- **FR-011**: System MUST expose the same stage status information through stdout for CLI users and automation logs.
- **FR-012**: System MUST add GitHub Actions CI for PR/main that runs pytest, ruff, and mypy without requiring apfel, Claude, Codex, private vault data, or local user credentials.
- **FR-013**: System MUST keep daily idempotent: rerunning on unchanged inputs must not create duplicate Cards, duplicate profile facts, or duplicate DailyReports for the same date beyond deterministic replacement/update behavior.
- **FR-014**: System MUST keep interactive/batch policy unchanged: `daily` remains batch and must not prompt for TTY confirmation.
- **FR-015**: System MUST avoid sending raw unredacted content to external providers while executing daily stages.

### Key Entities *(include if feature involves data)*

- **DailyStage**: A named pipeline step with description, dependencies, and an executable action.
- **StageResult**: The result of one stage execution, including status, elapsed seconds, summary counters, error message, and skip reason.
- **DailyRunReport**: Aggregate run record containing run date, selected resume target, stage results, total elapsed time, failure count, skipped count, new artifact counts, and estimated cost.
- **CIWorkflow**: Repository automation contract that defines when and how pytest, ruff, and mypy run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A forced classify failure marks all dependent stages skipped and returns exit code 1 in automated tests.
- **SC-002**: `daily --resume-from classify` executes no stages before classify and exposes those skipped stages in the summary.
- **SC-003**: Unknown resume stage names fail before execution with exit code 2 and a message listing valid stage names.
- **SC-004**: A successful no-op daily run on unchanged test fixtures is idempotent and produces no duplicate user-facing artifacts.
- **SC-005**: DailyReport generation includes every configured stage exactly once with status and elapsed seconds.
- **SC-006**: CI workflow completes mock-based pytest, ruff, and mypy checks without requiring local-only binaries or private user data.
- **SC-007**: Full local test suite remains green after the feature is implemented.

## Assumptions

- The stage order remains compatible with the current pipeline: collect, cluster, classify, generate, index, profile, report.
- Card generation depends on classification; indexing depends on generated or existing Cards; profile extraction can depend on raw collection and redaction availability.
- The current cost summary implementation is the source for estimated USD in DailyReport.
- DailyReport lives under the existing vault system area used by the cost observability work.
- CI should start with one Python version matching the supported floor, then expand later if needed.
