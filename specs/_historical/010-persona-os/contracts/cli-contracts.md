# CLI 계약: Persona OS

**기능**: 010-persona-os
**작성일**: 2026-05-13
**작성자**: JunyoungJung

Persona OS CLI는 `synapse-memory persona` 하위 명령으로만 노출한다. MVP 명령은 다섯 개를 넘지 않는다.

## 공통 계약

분류: interactive endpoint.

모든 Persona OS 명령은 다음을 만족해야 한다.

- `--vault <path>` optional override를 지원한다.
- vault path를 찾지 못하면 파일을 만들거나 수정하지 않고 `synapse-memory doctor` 안내를 출력한다.
- 사람 TTY에서 직접 실행될 때 기존 `_interactive_guard()` 정책을 따른다.
- `SYNAPSE_FROM_AGENT=1` 환경에서는 guard delay 없이 실행한다.
- raw user text와 file content를 stdout/stderr에 그대로 출력하지 않는다.

종료 코드:

| 상황 | 종료 코드 |
| --- | --- |
| 성공 | `0` |
| 사용자 입력/지원 형식 오류 | `2` |
| vault 또는 file system 오류 | `1` |
| AI provider/redaction 오류 | `1` |

## `synapse-memory persona start`

### 사용법

```bash
synapse-memory persona start [--vault <path>]
```

### 동작

- `<vault>/90_System/AI/Persona/`를 생성한다.
- 누락된 Persona 파일만 생성한다.
- 기존 Persona 파일을 덮어쓰지 않는다.
- pending claim 수와 다음 질문 1개를 출력한다.

### 출력 예시

```text
Persona OS ready
files_created=4 pending_claims=0
next_question: 내가 답변할 때 절대 추측하면 안 되는 주제나 상황은 무엇인가요?
```

## `synapse-memory persona add`

### 사용법

```bash
synapse-memory persona add "<답변>" [--file <path>]... [--vault <path>]
synapse-memory persona add --file <path> [--file <path>]... [--vault <path>]
```

### 지원 입력

| 입력 | 지원 여부 | 비고 |
| --- | --- | --- |
| direct text argument | yes | UTF-8 string |
| `.txt` | yes | UTF-8 decode with replacement |
| `.md` / `.markdown` | yes | UTF-8 decode with replacement |
| `.pdf` | no in MVP | 명확한 unsupported 안내 |
| binary files | no | fail-fast |

### 동작

- 입력을 하나의 evidence batch로 묶는다.
- raw content를 L0 private Persona evidence storage에 기록한다.
- redaction 후 `Persona/Inbox.md`에 pending claim 후보를 추가한다.
- `Profile.md`, `Voice.md`, `Boundaries.md`를 수정하지 않는다.

### 출력 예시

```text
Persona evidence added
evidence=2 pending_claims=3 conflicts=0
review: synapse-memory persona review
```

## `synapse-memory persona review`

### 사용법

```bash
synapse-memory persona review [--vault <path>]
synapse-memory persona review --accept <claim_id> [--vault <path>]
synapse-memory persona review --reject <claim_id> [--reason <text>] [--vault <path>]
```

### 동작

- 인자가 없으면 pending/conflicted claim 목록을 표시한다.
- `--accept`는 claim category에 따라 `Profile.md`, `Voice.md`, `Boundaries.md` 중 하나에 append한다.
- `--reject`는 claim을 rejected로 표시하고 optional reason을 기록한다.
- accepted/rejected provenance를 보존한다.

### 출력 예시

```text
Pending Persona claims
pc_20260513_001 [voice] confidence=0.82
  statement: 근거가 있는 짧은 답변을 선호한다.
  evidence: ev_20260513_001
```

## `synapse-memory persona next`

### 사용법

```bash
synapse-memory persona next [--vault <path>]
```

### 동작

- accepted/pending claim coverage를 계산한다.
- pending claim 수가 threshold 이상이면 review-first 안내를 출력한다.
- 그렇지 않으면 coverage gap 기반 질문 1개만 출력한다.

### 출력 예시

```text
next_question: 결정을 내릴 때 비용, 속도, 안정성 중 무엇을 가장 먼저 보나요?
category: decision_style
reason: decision_style accepted claim이 부족합니다.
```

## `synapse-memory persona simulate`

### 사용법

```bash
synapse-memory persona simulate "<상황>" [--vault <path>] [--model <model>]
```

### 동작

- accepted Persona files만 로드한다.
- `Boundaries.md`를 먼저 검사한다.
- evidence가 부족하면 답변 대신 다음 질문을 출력한다.
- 답변이 가능하면 claim id를 함께 출력한다.
- pending/rejected/conflicted claim은 prompt에 포함하지 않는다.

### 출력 예시

```text
status: answered
claims: pc_20260513_001, pc_20260513_004

면접에서는 먼저 실수를 인정하고, 그 뒤 재발 방지 구조를 설명하는 방식으로 답합니다...
```

거부 예시:

```text
status: refused
reason: Boundaries.md의 pc_20260513_007 규칙에 따라 이 상황은 추측으로 답하지 않습니다.
```
