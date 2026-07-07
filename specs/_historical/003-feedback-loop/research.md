# Phase 0 — Research: Feedback Loop

## R1. `feedback last` 의 대상 해석

- **Decision**: 답변을 생성하는 endpoint 가 성공 직후 `LastAnswerReference` 를 기록한다. 본문 전체는 저장하지 않고 answer id, command, citations, source ids, timestamp 만 저장한다.
- **Rationale**: `feedback last` 는 사용자가 직전 답변을 다시 지정하지 않게 하는 UX 기능이다. 답변 전문 저장은 privacy surface 를 넓히므로 피하고, 피드백 target 해석에 필요한 metadata 만 남긴다.
- **Alternatives considered**:
  - stdout 을 파싱하여 마지막 답변을 복원: shell/터미널별로 깨지기 쉬워 기각.
  - 답변 전문 저장: 디버깅에는 편하지만 private storage 면적이 커져 기각.

## R2. 이벤트 ID 형식

- **Decision**: `YYYYMMDDTHHMMSSffffffZ-<random_hex>` 형식의 sortable local id 를 사용한다.
- **Rationale**: 시간순 정렬 가능하고 표준 라이브러리만으로 생성할 수 있다. 새 ULID dependency 를 추가하지 않아 설치·검증 표면을 유지한다.
- **Alternatives considered**:
  - ULID library 추가: 부모 roadmap 의 예시와 맞지만 이 feature 만을 위해 새 dependency 를 추가하는 비용이 커서 기각.
  - UUID4 단독: 유일성은 충분하지만 파일 검토 시 시간순 파악이 어려워 기각.

## R3. feedback reason 처리

- **Decision**: feedback command 는 외부 LLM 을 호출하지 않는다. reason 은 저장 전 deterministic masking 과 길이 제한을 적용한다.
- **Rationale**: feedback 은 batch command 여야 하며 apfel/Claude 없이 동작해야 한다. reason 은 local private log 에만 저장되므로 trust boundary 를 넘지 않는다.
- **Alternatives considered**:
  - Pass2까지 실행: 개인정보 보호는 강해지지만 apfel 미설치 환경에서 핵심 feedback 기록이 막혀 기각.
  - raw reason 그대로 저장: local-only 라도 사용자가 tail/log 를 공유할 수 있어 기각.

## R4. 손상된 feedback log 복구

- **Decision**: reader 는 처음부터 JSONL 을 읽다가 첫 손상 라인을 만나면 readable prefix 는 유지하고 손상 라인부터 EOF 까지 `.bak` 파일로 이동한다.
- **Rationale**: append-only log 는 tail 쪽 부분 쓰기나 수동 편집으로 깨질 가능성이 높다. prefix 보존은 기존 신호 손실을 최소화한다.
- **Alternatives considered**:
  - 손상 라인만 skip: 이후 라인의 신뢰성을 알 수 없어 기각.
  - 전체 파일 폐기: 정상 이벤트 손실이 커서 기각.

## R5. card feedback score 산출

- **Decision**: card target event 를 시간순으로 적용해 score 를 `[0.5, 1.5]` 범위로 clamp 한다. reject 기본은 곱셈 0.85, accept 기본은 곱셈 1.10, explicit weight 는 `1.0 + weight` multiplier 로 반영한다.
- **Rationale**: 한 번의 실수로 card 가 영구 배제되지 않고, 반복 신호가 누적되며, 산출값이 retrieve 단계에서 직관적으로 곱해진다.
- **Alternatives considered**:
  - 선형 합산만 사용: 이벤트가 누적될수록 clamp 에 빨리 걸려 세밀한 차이가 줄어 기각.
  - embedding 자체 재작성: 비용과 복잡도가 커서 기각.

## R6. 적용 시점

- **Decision**: 인덱싱 시 card metadata 에 `feedback_score` 를 저장하고, retrieval 결과를 반환하기 직전 score 에 한 번 더 반영한다.
- **Rationale**: 인덱스 metadata 에 남기면 quickstart 에서 적용 여부를 검증하기 쉽고, query 후 보정은 기존 ChromaDB distance 를 파괴하지 않는다.
- **Alternatives considered**:
  - retrieval 단계에서 매번 feedback log 전체 읽기: 단순하지만 query latency 가 event 수에 비례해 기각.
  - daily 에서 Card markdown 을 수정: 사용자의 원본 지식 파일을 피드백 신호로 오염시켜 기각.

## R7. slash command surface

- **Decision**: `commands/synapse-feedback.md` 를 compatibility shim 으로 추가하고 `SYNAPSE_FROM_AGENT=1 synapse-memory feedback ...` 사용을 명시한다.
- **Rationale**: repo 정책은 skills-first 이지만 기존 slash command 사용자가 있고, feedback 은 사용자가 답변 직후 자주 호출할 명령이다.
- **Alternatives considered**:
  - CLI 문서만 추가: 답변 직후 마찰이 커져 기각.
