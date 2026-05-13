# 파일 계약: Persona OS

**기능**: 010-persona-os
**작성일**: 2026-05-13
**작성자**: JunyoungJung

## Vault-visible Persona directory

경로:

```text
<vault>/90_System/AI/Persona/
```

MVP 파일:

```text
Profile.md
Voice.md
Boundaries.md
Inbox.md
```

규칙:

- `persona start`는 누락된 파일만 생성한다.
- 기존 파일 내용은 덮어쓰지 않는다.
- raw user text와 file content는 이 directory에 그대로 쓰면 안 된다.
- Persona OS가 쓰는 영역은 marker로 구분한다.

## Managed section marker

모든 Persona OS managed writes는 다음 marker 안에서만 수행한다.

```text
<!-- PERSONA_OS:START -->
...
<!-- PERSONA_OS:END -->
```

파일에 marker가 없으면 파일 끝에 새 section을 추가한다. Marker 밖의 사용자 작성 내용은 그대로 보존한다.

## `Profile.md`

역할: 승인된 안정적 사용자 사실, 선호, work style, decision style.

기본 skeleton:

```markdown
# Persona Profile

사용자가 승인한 안정적 사실과 선호를 기록합니다.

<!-- PERSONA_OS:START -->
## Accepted Claims

<!-- PERSONA_OS:END -->
```

Accepted claim row:

```markdown
### pc_YYYYMMDD_NNN

- category: profile
- confidence: 0.82
- accepted_at: 2026-05-13T10:00:00
- evidence: ev_YYYYMMDD_NNN
- statement: 근거가 있는 짧은 답변을 선호한다.
```

## `Voice.md`

역할: 말투, 문장 길이, 선호/금지 표현.

Accepted claim row는 `category: voice`를 사용한다.

## `Boundaries.md`

역할: privacy, refusal, unknown-handling, 추측 금지 규칙.

Accepted claim row는 `category: boundary` 또는 `category: unknown_handling`을 사용한다.

`persona simulate`는 답변 생성 전에 이 파일의 accepted claim을 먼저 검사해야 한다.

## `Inbox.md`

역할: pending, conflicted, rejected claim 및 next question history.

기본 skeleton:

```markdown
# Persona Inbox

승인 대기 Persona 후보와 질문 기록을 검토합니다.

<!-- PERSONA_OS:START -->
## Pending Claims

## Conflicted Claims

## Rejected Claims

## Question History

<!-- PERSONA_OS:END -->
```

Pending claim row:

```markdown
### pc_YYYYMMDD_NNN

- status: pending
- category: voice
- confidence: 0.82
- created_at: 2026-05-13T10:00:00
- evidence: ev_YYYYMMDD_NNN
- statement: 근거가 있는 짧은 답변을 선호한다.
```

Rejected claim row:

```markdown
### pc_YYYYMMDD_NNN

- status: rejected
- category: voice
- decided_at: 2026-05-13T10:05:00
- reason: 지금 기준과 맞지 않음
- statement: 근거가 있는 짧은 답변을 선호한다.
```

Question history row:

```markdown
- pq_YYYYMMDD_NNN | 2026-05-13T10:10:00 | boundary | 내가 답변할 때 절대 추측하면 안 되는 주제나 상황은 무엇인가요?
```

## L0 private evidence storage

경로:

```text
~/.synapse/private/persona/
```

예상 파일:

```text
evidence.jsonl
raw/
└── <evidence_id>.txt
```

`evidence.jsonl` line shape:

```json
{"evidence_id":"ev_20260513_001","batch_id":"pb_20260513_001","source_kind":"text","source_ref":"direct-input","private_ref":"raw/ev_20260513_001.txt","redacted_summary":"...", "content_sha256":"...", "collected_at":"2026-05-13T10:00:00"}
```

규칙:

- Directory mode는 기존 L0 security policy를 따른다.
- Vault-visible Persona files는 `private_ref` path 전체 대신 evidence id와 짧은 source ref만 표시한다.
- Raw file content를 chat output, logs, vault-visible files에 그대로 노출하지 않는다.
