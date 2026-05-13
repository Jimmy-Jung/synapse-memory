# Feature Specification: Persona OS

**Feature Branch**: `010-persona-os`  
**Created**: 2026-05-13  
**Author**: JunyoungJung  
**Status**: Draft  
**Input**: User description: "Persona OS 이름으로, 사용자가 대화와 첨부를 지속적으로 제공하면 AI가 필요한 질문을 이어가며 사용자의 말투, 선호, 판단 기준, 금지 영역을 검토 가능한 형태로 축적한다. 스킬은 최대한 간소화한다."

## User Scenarios & Testing *(mandatory)*

Persona OS 는 "나를 완벽히 복제하는 모델" 이 아니라, 사용자가 승인한 자기 정보와 근거 자료를 기반으로 말투·판단·금지 영역을 관리하는 local-first personal context layer 다. MVP 는 skill 을 늘리지 않고 `skills/persona-os/SKILL.md` 한 개와 `synapse-memory persona ...` CLI 표면으로 제한한다.

### User Story 1 - Persona OS 세션 시작과 다음 질문 제안 (Priority: P1)

사용자는 `synapse-memory persona start` 로 Persona OS 를 시작하고, 시스템은 현재 승인된 Persona 자료와 pending 후보를 읽어 다음에 물어볼 질문 1개를 제안한다.

**Why this priority**: 첫 경험에서 "무엇을 입력해야 하는지"가 분명해야 지속 입력 루프가 시작된다. 질문 생성이 없으면 사용자는 빈 Profile 파일 앞에서 멈춘다.

**Independent Test**: 빈 fixture vault 에서 `persona start` 를 실행하면 `90_System/AI/Persona/` 디렉터리와 4개 파일이 생성되고, stdout 에 다음 질문 1개와 자료 추가 방법이 출력된다.

**Acceptance Scenarios**:

1. **Given** Persona OS 파일이 없다, **When** 사용자가 `persona start` 를 실행한다, **Then** `Profile.md`, `Voice.md`, `Boundaries.md`, `Inbox.md` 가 생성되고 다음 질문 1개가 출력된다.
2. **Given** 기존 Persona OS 파일이 있다, **When** 사용자가 `persona start` 를 다시 실행한다, **Then** 기존 파일을 덮어쓰지 않고 현재 pending 후보 수와 다음 질문만 출력한다.
3. **Given** vault 경로를 찾을 수 없다, **When** 사용자가 `persona start` 를 실행한다, **Then** 파일을 만들지 않고 `synapse-memory doctor` 또는 vault 설정 안내를 출력한다.

---

### User Story 2 - 답변과 첨부를 하나의 add 명령으로 누적 (Priority: P1)

사용자는 대화 중 답변을 직접 입력하거나 markdown/text/pdf 같은 파일을 첨부해 Persona OS 를 보강한다. 명령은 분산하지 않고 `persona add` 하나로 처리한다.

**Why this priority**: 스킬과 명령 표면을 줄이는 핵심이다. `answer`, `attach`, `import` 를 나누면 기능은 명확해 보이지만 실제 사용자는 어떤 명령을 골라야 할지 고민한다.

**Independent Test**: fixture vault 에서 `persona add "나는 긴 설명보다 근거 있는 짧은 답변을 선호한다"` 를 실행하면 raw 원본은 L0 private 영역에 저장되고, redacted 후보가 `Persona/Inbox.md` 에 append 된다.

**Acceptance Scenarios**:

1. **Given** 사용자가 텍스트 답변을 제공한다, **When** `persona add "<답변>"` 실행, **Then** 답변에서 추출된 PersonaClaim 후보가 `Inbox.md` 에 승인 대기 상태로 추가된다.
2. **Given** 사용자가 지원 파일을 제공한다, **When** `persona add --file <path>` 실행, **Then** 파일 내용은 L0 private 영역으로 mirror 되고 redaction 후 후보만 `Inbox.md` 에 추가된다.
3. **Given** 사용자가 답변과 파일을 함께 제공한다, **When** `persona add "<답변>" --file <path>` 실행, **Then** 두 입력은 같은 evidence batch 로 기록되어 중복 질문을 줄이는 데 사용된다.
4. **Given** 지원하지 않는 파일 형식이다, **When** `persona add --file <path>` 실행, **Then** 파일을 저장하지 않고 지원 형식과 대체 방법을 안내한다.

---

### User Story 3 - 승인 전 후보를 Profile 에 반영하지 않음 (Priority: P1)

Persona OS 는 AI가 추출한 성향 후보를 바로 진실원본에 쓰지 않는다. 사용자는 `persona review` 로 후보를 보고 수동 승인 또는 거절한다.

**Why this priority**: Synapse Memory 의 기존 MemoryInbox 원칙과 같다. 잘못 추출된 자기 정보가 즉시 "나"로 굳어지면 클론 품질과 신뢰가 무너진다.

**Independent Test**: `persona add` 후 `Persona/Profile.md` 는 변경되지 않고, `persona review --accept <claim_id>` 실행 후에만 승인된 claim 이 적절한 파일로 이동한다.

**Acceptance Scenarios**:

1. **Given** pending claim 이 있다, **When** 사용자가 `persona review` 를 실행한다, **Then** claim id, category, statement, confidence, evidence summary 가 표시된다.
2. **Given** 사용자가 claim 을 승인한다, **When** `persona review --accept <claim_id>` 실행, **Then** claim category 에 따라 `Profile.md`, `Voice.md`, 또는 `Boundaries.md` 에 반영된다.
3. **Given** 사용자가 claim 을 거절한다, **When** `persona review --reject <claim_id> --reason "<이유>"` 실행, **Then** claim 은 rejected 로 표시되고 다음 질문 생성에서 같은 후보를 반복하지 않는다.
4. **Given** 상충되는 claim 이 발견된다, **When** `persona review` 실행, **Then** `Inbox.md` 에 conflict 표시와 함께 사용자가 어느 쪽이 현재 기준인지 선택할 수 있게 한다.

---

### User Story 4 - 다음 질문은 coverage gap 기반으로 생성 (Priority: P2)

사용자는 `persona next` 로 다음에 답하면 좋은 질문을 받는다. 질문은 랜덤이 아니라 현재 부족한 Persona 영역을 기준으로 생성된다.

**Why this priority**: "꾸준하게 대화와 데이터 첨부를 통해 완성"하려면 시스템이 부족한 정보를 기억하고, 한 번에 하나씩 물어봐야 한다.

**Independent Test**: fixture vault 에 Voice 정보는 충분하지만 Boundaries 가 비어 있으면 `persona next` 는 말투 질문보다 금지 영역이나 추측 금지 규칙을 묻는 질문을 우선한다.

**Acceptance Scenarios**:

1. **Given** 특정 category 의 accepted claim 이 부족하다, **When** `persona next` 실행, **Then** 해당 category 를 보강하는 질문 1개가 출력된다.
2. **Given** pending claim 이 너무 많다, **When** `persona next` 실행, **Then** 새 질문보다 `persona review` 를 먼저 하라는 안내를 출력한다.
3. **Given** 최근에 같은 질문을 했다, **When** `persona next` 실행, **Then** 동일 질문 반복을 피하고 다른 각도의 질문을 생성한다.

---

### User Story 5 - 승인된 Persona 로 상황 시뮬레이션 (Priority: P2)

사용자는 `persona simulate "<상황>"` 으로 승인된 Persona 자료를 바탕으로 "나라면 어떻게 말할지/판단할지"를 확인한다.

**Why this priority**: Persona OS 의 가치를 체감하는 첫 output 이다. 단, 근거가 부족하면 그럴듯하게 꾸미지 말고 부족한 정보를 물어야 한다.

**Independent Test**: 승인된 Voice 와 Boundaries 가 있는 fixture vault 에서 `persona simulate "면접에서 실패 경험을 묻는다면"` 을 실행하면 Profile/Voice/Boundaries 를 prompt 에 포함하고, 응답에 사용한 근거 claim id 를 표시한다.

**Acceptance Scenarios**:

1. **Given** 충분한 승인 자료가 있다, **When** `persona simulate "<상황>"` 실행, **Then** 상황에 맞는 응답 초안과 근거 claim id 가 출력된다.
2. **Given** 근거가 부족하다, **When** `persona simulate "<상황>"` 실행, **Then** 추측성 답변 대신 부족한 정보와 다음 질문을 출력한다.
3. **Given** 상황이 Boundaries 에서 금지한 영역이다, **When** `persona simulate "<상황>"` 실행, **Then** 답변을 거부하거나 사용자 확인을 요구한다.

---

### User Story 6 - 스킬 표면 최소화 (Priority: P3)

메인테이너는 Persona OS 를 위해 여러 skill 을 만들지 않는다. `skills/persona-os/SKILL.md` 하나가 모든 Persona OS 행동 지침과 CLI 매핑을 담는다.

**Why this priority**: 스킬이 늘어나면 사용자는 무엇을 호출해야 하는지 모르고, Codex/Claude 표면 유지보수도 커진다. 기능 확장은 skill 추가가 아니라 CLI, data model, recipe 확장으로 처리한다.

**Independent Test**: plugin packaging 또는 skill discovery 검증에서 Persona OS 관련 skill 은 정확히 1개만 노출되고, 해당 skill 안에 start/add/next/review/simulate 명령 매핑이 모두 있다.

**Acceptance Scenarios**:

1. **Given** Persona OS 기능이 설치되어 있다, **When** skill 목록을 확인한다, **Then** Persona OS 관련 skill 은 `persona-os` 하나만 존재한다.
2. **Given** 새 Persona OS 기능이 추가된다, **When** 문서를 갱신한다, **Then** 별도 skill 추가 없이 기존 `persona-os` skill 의 명령 매핑만 갱신한다.

## Pseudocode *(design contract)*

```python
def persona_start(vault):
    ensure_persona_files(vault, overwrite=False)
    pending_count = count_pending_claims(vault)
    question = select_next_question(vault)
    return PersonaStartResult(pending_count=pending_count, question=question)


def persona_add(vault, text=None, files=()):
    batch = create_evidence_batch()
    if text:
        batch.add_text(text)
    for path in files:
        batch.add_file(mirror_to_l0_private(path))

    redacted_items = redact_batch(batch)
    claims = extract_persona_claims(redacted_items)
    conflicts = detect_claim_conflicts(vault, claims)
    append_persona_inbox(vault, claims, conflicts)
    return PersonaAddResult(claim_count=len(claims), conflict_count=len(conflicts))


def persona_next(vault):
    if count_pending_claims(vault) >= PENDING_REVIEW_LIMIT:
        return ReviewFirstMessage()

    coverage = score_persona_coverage(vault)
    gap = choose_highest_value_gap(coverage)
    question = generate_one_question(gap, avoid_recent=True)
    return PersonaQuestion(question=question, gap=gap)


def persona_review(vault, action=None, claim_id=None, reason=None):
    if action is None:
        return list_pending_claims(vault)

    claim = load_pending_claim(vault, claim_id)
    if action == "accept":
        target = resolve_persona_target_file(claim.category)
        append_accepted_claim(target, claim)
    elif action == "reject":
        mark_claim_rejected(vault, claim_id, reason)
    return ReviewResult(action=action, claim_id=claim_id)


def persona_simulate(vault, situation):
    persona_context = load_accepted_persona_context(vault)
    boundary_result = check_boundaries(persona_context.boundaries, situation)
    if boundary_result.requires_refusal:
        return BoundaryRefusal(boundary_result.reason)

    evidence = retrieve_relevant_persona_claims(persona_context, situation)
    if not enough_evidence(evidence):
        return NeedMoreInfo(next_question=generate_one_question_for_situation(situation))

    return generate_grounded_response(situation, persona_context, evidence)
```

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose exactly five MVP CLI commands: `persona start`, `persona add`, `persona next`, `persona review`, `persona simulate`.
- **FR-002**: System MUST use a single Persona OS skill file at `skills/persona-os/SKILL.md`. Additional Persona OS skill files are out of scope for MVP.
- **FR-003**: `persona start` MUST create the Persona directory and files if missing: `90_System/AI/Persona/Profile.md`, `Voice.md`, `Boundaries.md`, `Inbox.md`.
- **FR-004**: `persona start` MUST NOT overwrite existing Persona files.
- **FR-005**: `persona add` MUST accept text input, one or more supported file paths, or both in one invocation.
- **FR-006**: Raw text and file contents MUST be stored only in L0 private storage. Vault-visible Persona files MUST contain redacted summaries, claim statements, and evidence references only.
- **FR-007**: All payloads sent to an external LLM MUST pass through the existing redaction pipeline. Raw content MUST NOT bypass redaction.
- **FR-008**: Extracted Persona claims MUST be written to `Persona/Inbox.md` as pending candidates and MUST NOT modify `Profile.md`, `Voice.md`, or `Boundaries.md` until accepted.
- **FR-009**: `persona review` MUST support listing pending claims, accepting a claim, and rejecting a claim with an optional reason.
- **FR-010**: Accepted claims MUST be routed by category: stable user facts and preferences to `Profile.md`, writing style to `Voice.md`, and refusal/privacy/unknown-handling rules to `Boundaries.md`.
- **FR-011**: `persona next` MUST generate one question at a time and SHOULD prioritize the highest-value coverage gap.
- **FR-012**: If pending claim count exceeds a documented threshold, `persona next` MUST ask the user to review pending claims before collecting more data.
- **FR-013**: `persona simulate` MUST use only accepted Persona files and cited evidence. Pending claims MUST NOT affect simulation output.
- **FR-014**: `persona simulate` MUST refuse or ask for clarification when accepted Persona evidence is insufficient.
- **FR-015**: `persona simulate` MUST respect `Boundaries.md` before generating an answer.
- **FR-016**: Every accepted or rejected claim MUST keep provenance: claim id, created date, evidence references, decision date, and optional reason.
- **FR-017**: Existing `Profile.md` and `DecisionPatterns.md` outside `90_System/AI/Persona/` MUST remain backward compatible. Persona OS MAY read them as context but MUST NOT migrate or delete them in MVP.
- **FR-018**: Persona OS commands MUST use the existing interactive endpoint guard policy where applicable.

### Non-Functional Requirements

- **NFR-001**: The MVP command surface must be understandable without reading implementation docs: five commands maximum.
- **NFR-002**: Persona file formats must be markdown-first and readable in Obsidian.
- **NFR-003**: Persona OS must be local-first by default and compatible with existing Synapse redaction guarantees.
- **NFR-004**: `persona next` and `persona review` should return within 1 second for up to 200 pending claims.
- **NFR-005**: Tests must cover file creation, non-overwrite behavior, pending-to-accepted flow, boundary refusal, and raw data redaction boundary.

## Key Entities *(data related)*

- **PersonaEvidence**: `{evidence_id, source_kind, source_ref, collected_at, redacted_summary, private_ref}`. Raw content is referenced by `private_ref` and remains in L0.
- **PersonaClaim**: `{claim_id, category, statement, confidence, evidence_ids, status, created_at, decided_at, reason}`. Status is `pending`, `accepted`, `rejected`, or `conflicted`.
- **PersonaCoverage**: Computed, not necessarily persisted. Tracks coverage for `profile`, `voice`, `boundaries`, `decision_style`, `work_style`, and `unknown_handling`.
- **PersonaQuestion**: `{question_id, category, question, reason, created_at}`. Used to avoid repeated questions.

## Minimal File Surface

```text
90_System/AI/Persona/
├── Profile.md
├── Voice.md
├── Boundaries.md
└── Inbox.md
```

## Minimal Skill Surface

```text
skills/persona-os/SKILL.md
```

The skill describes when to use Persona OS, safety rules, and command mapping only. It does not duplicate implementation details from this spec.

## Edge Cases

- Persona files exist but are partially missing: `persona start` recreates only missing files.
- `Inbox.md` has manually edited content: parser preserves unknown markdown sections and appends new candidates under a managed section.
- Same statement appears twice from different evidence: merge into one pending claim with multiple evidence ids where possible.
- A new claim conflicts with an accepted claim: mark as `conflicted` in `Inbox.md`; do not overwrite accepted material.
- File path points outside user-readable location or cannot be opened: fail before writing any batch entry.
- Redaction returns empty content: do not call external LLM; tell the user no safe content remains.
- Simulation asks for a domain with no accepted evidence: ask a follow-up question instead of inventing a persona answer.
- User rejects a claim without reason: allow it, but record an empty reason explicitly.
- User deletes Persona directory: `persona start` can recreate skeleton, but old accepted claims are not reconstructed unless existing sources are reprocessed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh fixture vault can run `persona start` and produce the four-file Persona skeleton without overwriting existing user content.
- **SC-002**: `persona add` with text creates at least one pending claim in `Inbox.md` while leaving `Profile.md`, `Voice.md`, and `Boundaries.md` unchanged.
- **SC-003**: `persona review --accept <claim_id>` moves the accepted claim into the correct Persona file and records provenance.
- **SC-004**: `persona simulate` uses accepted claims only, with claim ids shown in the output or last-answer metadata.
- **SC-005**: A boundary rule accepted into `Boundaries.md` prevents `persona simulate` from generating an answer that violates that rule.
- **SC-006**: Persona OS exposes one skill file and five MVP CLI commands; adding the feature does not create multiple Persona-specific skills.
- **SC-007**: Tests prove raw input text and supported file contents are never written verbatim into vault-visible Persona files.

## Assumptions

- Existing Synapse vault detection, L0 private storage, redaction, and LLM provider abstractions are reused.
- Existing `90_System/AI/Profile.md` and `DecisionPatterns.md` remain supported for legacy `me` commands.
- The first implementation may support only plain text and markdown attachments. PDF support may be added in a later task if parser dependencies are not already available.
- Persona OS is single-user and single-vault in MVP.
- Slash commands may be added later, but MVP can ship with CLI plus one skill file.
