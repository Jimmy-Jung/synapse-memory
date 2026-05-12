# Phase 1 — Data Model: Feedback Loop

## Entity: FeedbackEvent

```python
@dataclass(frozen=True)
class FeedbackEvent:
    event_id: str
    ts: datetime
    target_kind: Literal["answer", "card", "pattern"]
    target_ref: str
    action: Literal["accept", "reject", "weight"]
    weight: float
    reason: str | None
    answer_id_context: str | None
```

- **생성자**: `synapse-memory feedback ...`
- **저장 위치**: `~/.synapse/private/feedback.jsonl`
- **불변성**: 기존 event 수정 금지. 정정은 새 event 로 기록.
- **검증**:
  - `target_ref` 는 비어 있을 수 없다.
  - `action=reject` 는 non-empty reason 필요.
  - `weight` 는 `[-1.0, 1.0]`.
  - `reason` 은 저장 전 masking 되고 최대 500자.

## Entity: LastAnswerReference

```python
@dataclass(frozen=True)
class LastAnswerReference:
    answer_id: str
    ts: datetime
    command: Literal["ask", "me.what_did_i_think", "me.decide"]
    query: str
    citations: tuple[AnswerCitation, ...]
    session_id: str | None
```

- **생성자**: 답변 생성 endpoint 성공 직후 best-effort write.
- **저장 위치**: `~/.synapse/private/last_response.json`
- **본문 저장 금지**: AI 답변 전문은 저장하지 않는다.
- **수명**: 마지막 답변 1건만 보존.

## Entity: AnswerCitation

```python
@dataclass(frozen=True)
class AnswerCitation:
    target_kind: Literal["card", "pattern"]
    target_ref: str
    source_kind: str
    display_name: str
```

- `feedback last` 가 기본 target 을 해석할 때 사용한다.
- 하나의 답변이 여러 citation 을 가질 수 있다.

## Entity: FeedbackTarget

```python
@dataclass(frozen=True)
class FeedbackTarget:
    target_kind: Literal["answer", "card", "pattern"]
    target_ref: str
    display_name: str
```

- CLI validation 결과로 생성되는 내부 표현.
- direct card/pattern feedback 은 존재 확인 후 생성한다.

## Entity: FeedbackAggregate

```python
@dataclass(frozen=True)
class FeedbackAggregate:
    target_kind: Literal["card", "pattern"]
    target_ref: str
    score: float
    events_count: int
    last_event_ts: datetime | None
```

- **card score 범위**: `[0.5, 1.5]`
- **기본값**: 이벤트가 없으면 `1.0`
- **상태 전이**:

```text
score=1.0
reject(default -0.3)  -> max(0.5, score * 0.85)
accept(default +0.2)  -> min(1.5, score * 1.10)
weight(delta)         -> clamp(score * (1.0 + delta), 0.5, 1.5)
```

## Relationships

```text
LastAnswerReference 1 ──> many AnswerCitation
FeedbackEvent       many ──> 1 FeedbackTarget
FeedbackEvent       many ──> 1 FeedbackAggregate
FeedbackAggregate   1 ──> Card retrieval metadata
```

## Entity: DecisionPatternReference

```python
@dataclass(frozen=True)
class DecisionPatternReference:
    pattern_id: str
    trigger: str
    action: str
    display_name: str
```

- `pattern_id` 는 사용자가 검토한 DecisionPatterns 문서에서 안정적으로 해석되는 id 이다.
- 명시 id 가 없는 기존 패턴은 trigger/action 기반 deterministic slug 를 사용할 수 있다.

## Validation Rules

- feedback event 는 1줄 JSON object 로 직렬화 가능해야 한다.
- JSONL reader 는 손상 라인을 발견하면 readable prefix 를 먼저 보존한다.
- direct card target 은 ProjectCard/CompanyCard 또는 vector metadata 에서 확인 가능한 id 여야 한다.
- pattern target 은 DecisionPatternReference 로 해석 가능한 경우에만 기록한다.
