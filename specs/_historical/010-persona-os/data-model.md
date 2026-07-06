# 데이터 모델: Persona OS

**기능**: 010-persona-os
**작성일**: 2026-05-13
**작성자**: JunyoungJung

## PersonaEvidence

사용자가 `persona add`로 제공한 답변 또는 지원 첨부의 redacted evidence record다. Raw content는 vault에 쓰지 않고 L0 private storage에만 보관한다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `evidence_id` | string | yes | `ev_` prefix + stable random/hashed suffix. |
| `batch_id` | string | yes | 같은 `persona add` 호출에서 들어온 입력을 묶는다. |
| `source_kind` | enum | yes | `text`, `file_text`, `file_markdown`. |
| `source_ref` | string | yes | 사용자 표시용 짧은 출처. File은 basename만 허용. |
| `private_ref` | path/string | yes | `~/.synapse/private/persona/` 아래 raw mirror 경로 또는 jsonl offset. |
| `redacted_summary` | string | yes | vault-visible 요약. Raw 원문과 동일하면 안 된다. |
| `content_sha256` | string | yes | 중복 방지용 hash. Raw text 자체를 대체한다. |
| `collected_at` | datetime | yes | ISO 8601 local timestamp. |

규칙:

- `private_ref`는 vault 경로를 가리키면 안 된다.
- `redacted_summary`가 비어 있으면 claim extraction을 실행하지 않는다.
- 같은 `content_sha256`이 이미 있으면 새 evidence를 만들지 않고 기존 evidence id를 재사용할 수 있다.

## PersonaClaim

AI 또는 deterministic extractor가 evidence에서 뽑은 Persona 후보 또는 승인된 claim이다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `claim_id` | string | yes | `pc_` prefix + stable id. |
| `category` | enum | yes | `profile`, `voice`, `boundary`, `decision_style`, `work_style`, `unknown_handling`. |
| `statement` | string | yes | 사람이 읽을 수 있는 한국어 우선 문장. |
| `confidence` | float | yes | 0.0 이상 1.0 이하. |
| `evidence_ids` | list[string] | yes | 하나 이상. |
| `status` | enum | yes | `pending`, `accepted`, `rejected`, `conflicted`. |
| `created_at` | datetime | yes | claim 생성 시각. |
| `decided_at` | datetime | no | accepted/rejected 전이 시각. |
| `reason` | string | no | reject reason 또는 conflict 설명. |
| `target_file` | enum | no | accepted 후 `Profile.md`, `Voice.md`, `Boundaries.md` 중 하나. |

상태 전이:

```text
pending
  → accepted

pending
  → rejected

pending
  → conflicted
  → accepted

conflicted
  → rejected
```

규칙:

- `accepted` claim은 `target_file`과 `decided_at`이 필수다.
- `rejected` claim은 `decided_at`이 필수이고 `reason`은 빈 문자열일 수 있다.
- `conflicted` claim은 existing accepted claim id 또는 conflict 설명을 `reason`에 가져야 한다.
- `pending`과 `conflicted` claim은 simulation prompt에 포함하지 않는다.

## PersonaFileSet

Vault-visible Persona OS 파일 묶음이다.

| 파일 | 역할 | 쓰기 정책 |
| --- | --- | --- |
| `Profile.md` | 승인된 안정적 사실, 선호, work/decision style | `persona review --accept`만 managed section에 append |
| `Voice.md` | 말투, 문장 길이, 어조, 표현 금지/선호 | `persona review --accept`만 managed section에 append |
| `Boundaries.md` | 답변 거부 조건, privacy, unknown-handling | `persona review --accept`만 managed section에 append |
| `Inbox.md` | pending/rejected/conflicted 후보와 다음 질문 | `persona add`, `persona review`, `persona next`가 managed section 갱신 |

관리 섹션:

```text
<!-- PERSONA_OS:START -->
...
<!-- PERSONA_OS:END -->
```

규칙:

- 파일이 이미 있으면 marker 밖 사용자 내용을 보존한다.
- marker가 없으면 파일 끝에 managed section을 추가한다.
- `persona start`는 missing file만 생성하고 기존 파일을 덮어쓰지 않는다.

## PersonaCoverage

현재 accepted claim 분포를 바탕으로 계산되는 transient score다. MVP에서는 파일로 영속화하지 않는다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `category` | enum | yes | PersonaClaim.category와 동일한 축. |
| `accepted_count` | integer | yes | 0 이상. |
| `pending_count` | integer | yes | 0 이상. |
| `coverage_score` | float | yes | 0.0 이상 1.0 이하. |
| `next_question_priority` | integer | yes | 낮을수록 우선. |
| `reason` | string | yes | 왜 이 category를 물어야 하는지. |

기본 coverage 축:

```text
profile
voice
boundary
decision_style
work_style
unknown_handling
```

## PersonaQuestion

`persona next` 또는 evidence 부족 simulation이 제안한 질문이다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `question_id` | string | yes | `pq_` prefix. |
| `category` | enum | yes | 질문이 보강할 coverage category. |
| `question` | string | yes | 사용자에게 그대로 보여줄 질문 한 개. |
| `reason` | string | yes | 질문 선택 이유. |
| `created_at` | datetime | yes | 생성 시각. |
| `source` | enum | yes | `start`, `next`, `simulate`. |

규칙:

- 한 번에 하나의 질문만 출력한다.
- 최근 질문과 동일한 문자열을 반복하지 않는다.
- pending claim threshold를 넘으면 새 질문 대신 review-first 메시지를 반환한다.

## PersonaSimulationResult

`persona simulate`의 결과다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `status` | enum | yes | `answered`, `need_more_info`, `refused`. |
| `situation` | string | yes | 사용자 입력 상황. |
| `answer_markdown` | string | no | `answered`일 때 필수. |
| `claim_ids` | list[string] | yes | 답변에 사용한 accepted claim ids. |
| `next_question` | PersonaQuestion | no | `need_more_info`일 때 필수. |
| `refusal_reason` | string | no | `refused`일 때 필수. |

규칙:

- `answered`는 accepted claim id를 하나 이상 가져야 한다.
- `refused`는 `Boundaries.md`에 있는 accepted boundary claim을 근거로 해야 한다.
- `need_more_info`는 PersonaQuestion을 함께 반환해야 한다.
