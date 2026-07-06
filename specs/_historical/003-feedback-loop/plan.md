# Implementation Plan: Feedback Loop

**Branch**: `003-feedback-loop` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/003-feedback-loop/spec.md`

## Summary

Synapse Memory 사용자가 직전 AI 답변, 특정 Card, 특정 DecisionPattern 에 accept/reject/weight 피드백을 남기면 로컬 private feedback log 에 append-only 이벤트로 기록하고, 다음 인덱싱·검색에서 card 별 가중치로 반영한다. 구현은 새 외부 의존성 없이 `feedback` 도메인 모듈, 직전 답변 참조 저장소, CLI subcommand, RAG score 보정으로 구성한다.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: 기존 표준 라이브러리, `pydantic`, `chromadb`, `sentence-transformers`; 신규 외부 의존성 없음  
**Storage**: `~/.synapse/private/feedback.jsonl`, `~/.synapse/private/last_response.json`, ChromaDB card metadata 의 `feedback_score`  
**Testing**: pytest, ruff, mypy strict, redaction golden eval  
**Target Platform**: macOS 26 Tahoe + Apple Silicon  
**Project Type**: Python CLI/library  
**Performance Goals**: feedback record p95 ≤ 200ms, 1,000 events aggregation ≤ 500ms, retrieval score 보정 ≤ 10ms for top-100 results  
**Constraints**: local-first, append-only event log, feedback command은 batch endpoint, feedback reason 은 외부 LLM 송신 금지, code change 는 test-first, redaction F1 회귀 없음  
**Scale/Scope**: 단일 사용자, Card 50~500개, feedback event 0~5,000건

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 계획상 준수 방식 | 위험 / 완화 |
|---|---|---|
| I. Local-First & Privacy by Default | 모든 feedback/last-response 파일은 `~/.synapse/private/` 하위에 생성하고 권한을 0600/0700으로 유지한다. | feedback reason 에 민감정보가 포함될 수 있음 → 저장 전 deterministic masking 적용, 외부 송신 금지. |
| II. Two-Pass Redaction | 이 feature 는 외부 LLM payload 를 새로 만들지 않는다. feedback reason 은 local private 저장용이며 외부 trust boundary 를 넘지 않는다. | 향후 feedback summary 를 LLM에 보내는 기능이 생기면 Pass1+Pass2 gate 필수로 별도 spec 처리. |
| III. Test-First Discipline | feedback writer, corruption recovery, CLI validation, last response tracking, RAG weighting 모두 실패 테스트를 먼저 작성한다. | 구현 shortcut 위험 → tasks.md 에 test task 를 각 user story 앞에 배치. |
| IV. Conversation-Context-Aware Endpoints | `feedback` 은 batch endpoint 로 분류하여 TTY prompt 없이 실행한다. `ask`/`me`는 답변 완료 후 last-response metadata 만 남긴다. | interactive endpoint 에 부수효과 추가 → 실패 시 답변 자체는 성공해야 하므로 last-response write failure 는 warning 수준으로 격리. |
| V. Reproducible Daily Pipeline & Observability | feedback event 는 append-only, 인덱싱 적용은 결정적 집계 함수로 수행한다. | 손상 로그가 daily index 를 깨뜨릴 수 있음 → readable prefix 보존 + backup recovery 후 계속. |

**게이트 결과 (사전)**: 통과. Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/003-feedback-loop/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-contracts.md
│   └── file-contracts.md
└── tasks.md
```

### Source Code (repository root)

```text
src/synapse_memory/
├── cli.py                         # feedback subcommand 추가
├── endpoints/
│   ├── ask.py                     # successful answer 후 last-response 기록
│   └── me.py                      # what_did_i_think / decide 후 last-response 기록
├── feedback/
│   ├── __init__.py
│   ├── events.py                  # FeedbackEvent 생성·검증·append/recover
│   ├── targets.py                 # card/pattern/last target 해석
│   └── apply.py                   # card feedback_score 집계
├── rag/
│   ├── indexer.py                 # card metadata 에 feedback_score 반영
│   └── vector_store.py            # query 결과 score 보정 hook
├── profile/
│   └── patterns.py                # DecisionPatterns.md pattern id 해석
└── storage/
    └── last_response.py           # LastAnswerReference read/write

tests/
├── test_feedback_events.py
├── test_feedback_targets.py
├── test_feedback_apply.py
├── test_feedback_cli.py
├── test_last_response.py
├── test_profile_patterns.py
├── test_endpoints_ask.py
├── test_endpoints_me_extra.py
├── test_rag_indexer.py
└── test_rag_vector_store.py

commands/
└── synapse-feedback.md            # slash command compatibility surface

docs/
└── commands.md                    # CLI 문서 업데이트
```

**Structure Decision**: 새 도메인 경계는 `feedback/` 으로 분리한다. 직전 답변 참조는 여러 endpoint 에서 공유되므로 `storage/last_response.py` 에 둔다. RAG 쪽은 기존 `indexer.py`/`vector_store.py` 의 확장 지점만 건드리고, Card 본문 파일은 직접 수정하지 않는다.

## Phase 0 산출물

See [research.md](./research.md).

## Phase 1 산출물

- [data-model.md](./data-model.md)
- [contracts/cli-contracts.md](./contracts/cli-contracts.md)
- [contracts/file-contracts.md](./contracts/file-contracts.md)
- [quickstart.md](./quickstart.md)

## Constitution Check (post-design re-check)

| 원칙 | 재확인 결과 |
|---|---|
| I. Local-First & Privacy by Default | 통과. 모든 신규 파일은 L0 private 하위이며 file contract 에 권한을 명시했다. |
| II. Two-Pass Redaction | 통과. 외부 LLM 신규 payload 없음. feedback reason 은 local-only deterministic masking 이며 외부 송신하지 않는다. |
| III. Test-First Discipline | 통과. tasks 단계에서 각 slice 의 테스트를 구현보다 먼저 배치한다. |
| IV. Conversation-Context-Aware Endpoints | 통과. `feedback` 은 batch, `ask`/`me` 는 기존 interactive 정책 유지. |
| V. Reproducible Daily Pipeline & Observability | 통과. append-only event 와 deterministic aggregate 로 재실행 결과를 안정화한다. |

**최종 게이트 결과**: 통과. Complexity Tracking 불필요.

## Complexity Tracking

위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
