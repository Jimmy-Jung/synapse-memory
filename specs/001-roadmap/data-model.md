# Phase 1 — Data Model

본 문서는 spec §"Key Entities" 의 7개 entity 와 기존 entity 의 확장 필드를 Python dataclass 형태로 정의한다. 각 entity 의 *저장 위치*·*생성 주체*·*수명* 은 헌법 §"Trust boundary inventory" 와 일치하도록 명시한다.

## 표기 규약

- `Path` = `pathlib.Path`
- `datetime` = UTC ISO-8601 (예: `2026-05-12T14:23:55Z`)
- `Date` = `YYYY-MM-DD`
- `Decimal4` = 4자리 정밀도 float
- 모든 dataclass 는 `frozen=True` 권장 (immutability)

---

## 신규 Entity

### 1. FeedbackEvent

```python
@dataclass(frozen=True)
class FeedbackEvent:
    event_id: str               # ULID
    ts: datetime                # UTC
    target_kind: Literal["answer", "pattern", "card"]
    target_ref: str             # answer_id | pattern_id | card_id
    action: Literal["accept", "reject"]
    weight: float               # [-1.0, 1.0] (reject 기본 -0.3, accept +0.2)
    reason: str | None          # 사용자가 입력한 자유 텍스트 (max 500자, redacted)
    answer_id_context: str | None  # target_kind != "answer" 일 때, 어떤 답변 맥락에서 나왔는지
```

- **저장**: `~/.synapse/private/feedback.jsonl` (append-only, 0600)
- **생성자**: `synapse-memory feedback ...` 명령
- **수명**: 영구. v0.8 의 decay 가 적용 가능하나 event 자체는 보존.
- **헌법 매핑**: 원칙 I (L0), 원칙 II (reason 필드는 redacted 후 저장).

### 2. CostEvent

```python
@dataclass(frozen=True)
class CostEvent:
    event_id: str               # ULID
    ts: datetime
    command: str                # "ask" | "me decide" | "daily.classify" | ...
    model: str                  # "claude-opus-4-7" | "apfel" | ...
    input_tokens: int
    output_tokens: int
    usd: Decimal4 | None        # 단가표 미존재 시 None
    elapsed_s: float
    exit_code: int              # 0 = success
    error_class: str | None     # 예: "ApfelTimeout"
```

- **저장**: `~/.synapse/private/cost.jsonl` (append-only, 0600)
- **생성자**: `llm/apfel.py:complete()`, `llm/claude.py:complete()` 마무리 hook
- **수명**: 1년 후 자동 회전(`cost.YYYY.jsonl`).

### 3. DailyReport

vault markdown 파일. frontmatter 형식:

```yaml
---
date: 2026-05-12
total_elapsed_s: 93.8
errors_count: 0
new_cards: 1
new_facts: 15
est_usd: 0.42
stages:
  - name: collect_claude_code
    elapsed_s: 0.0
    status: ok
    summary: "변경 없음"
  - name: collect_obsidian
    elapsed_s: 0.2
    status: ok
    summary: "scanned=1356 mirrored=3"
  - name: classify
    elapsed_s: 0.8
    status: ok
    summary: "신규 cluster 없음"
  - name: generate
    elapsed_s: 18.7
    status: ok
    summary: "신규 Card 1개"
  - name: index
    elapsed_s: 26.5
    status: ok
    summary: "project=11 company=2"
  - name: update_profile
    elapsed_s: 47.6
    status: ok
    summary: "fact=15 → MemoryInbox PR"
---
```

- **저장**: `<vault>/90_System/AI/DailyReports/YYYY-MM-DD.md`
- **생성자**: `daily.py` 종료 시
- **수명**: 영구. vault 사용자 검토 대상.

### 4. SessionTurn

```python
@dataclass(frozen=True)
class SessionTurn:
    turn_idx: int               # 0-based
    ts: datetime
    role: Literal["user", "assistant", "system"]
    text: str                   # redacted
    citations: list[str]        # card_id 또는 chunk_id
    cost_event_id: str | None   # role="assistant" 일 때 연관 CostEvent
```

- **저장**: `~/.synapse/private/sessions/<session_id>.jsonl` (0600)
- **회전**: 50 턴 또는 1MB 초과 시 `<session_id>.001.jsonl` (Edge Case)
- **생성자**: `endpoints/session.py:append_turn()`

### 5. RawChunk (RAG)

```python
@dataclass(frozen=True)
class RawChunk:
    chunk_id: str               # f"{source_kind}:{path_hash}:{chunk_index}"
    source_kind: Literal["raw_obsidian", "raw_claude_code"]
    path: str                   # repo-relative or L0-relative path
    chunk_index: int
    text_redacted: str          # Pass1+Pass2 통과 후
    created: datetime
    embedding: list[float]      # bge-m3 1024-dim, ChromaDB 에 저장
```

- **저장**: ChromaDB collection `chunks` (Card 인덱스와 분리)
- **메타데이터** (ChromaDB metadata 한계 준수, R-B2):
  - `source_kind`, `path`, `chunk_index`, `created`

### 6. ProfileFactExtended (기존 확장)

기존 ProfileFact 필드에 추가:

```python
last_validated_at: datetime | None   # 마지막 사용자 검증 시각
validation_history: list[dict] = []  # [{ts, delta, reason}, ...] sidecar jsonl
conflicts_with: list[str] = []        # 다른 fact_id 목록
decay_applied_at: datetime | None    # 마지막 decay 적용 시각
```

- **sidecar jsonl** (R-B2): `~/.synapse/private/profile/fact_history/<fact_id>.jsonl`
- ProfileFactExtended.validation_history 는 메모리 상에서만 list, 디스크에는 jsonl.

### 7. DecisionPatternExtended (기존 확장)

```python
last_validated_at: datetime | None
validation_history: list[dict] = []
decay_applied_at: datetime | None
outcome_history: list[dict] = []  # [{ts, outcome: "good"|"bad", decision_ref}]
```

- **sidecar jsonl**: `~/.synapse/private/profile/pattern_history/<pattern_id>.jsonl`

---

## 상태 전이

### DailyReport.stages[*].status

```
ok       — 정상 완료
skipped  — 의존 stage 실패 (required_for 위반)
failed   — 예외 발생 (errors_count++ 트리거)
```

### FeedbackEvent → Card.feedback_score

```
event(reject, weight=-0.3) → card.events += 1, card.feedback_score = max(0.5, prev * 0.85)
event(accept, weight=+0.2) → card.feedback_score = min(1.5, prev * 1.10)
```

집계는 인덱싱 시 batch 로 수행 (R2).

### SessionTurn — 회전 정책

```
turn_idx 50 도달 또는 file 1MB 초과
  → 현재 jsonl 을 sessions/<id>.<rev:03d>.jsonl 로 rename
  → 새 sessions/<id>.jsonl 시작
  → rev=000 이 가장 오래된 파일
```

---

## 검증 규칙 (Pydantic / validator 권장)

- `FeedbackEvent.weight ∈ [-1.0, 1.0]`
- `CostEvent.input_tokens >= 0`, `output_tokens >= 0`, `elapsed_s >= 0`
- `SessionTurn.text` 가 외부 LLM 으로 흐를 때만 redacted 강제 (role=user/assistant). system prompt 는 본 라이브러리 소유 → 별도.
- `RawChunk.text_redacted` 는 Pass1+Pass2 통과한 결과만 허용 → ChromaDB upsert 전 assertion.

---

## 관계도

```text
FeedbackEvent ─→ Card.feedback_score (집계, 인덱싱 시점 적용)
              ─→ DecisionPattern.confidence (FR-D4 outcome)
              ─→ ProfileFact.last_validated_at

CostEvent     ─→ DailyReport.est_usd (일별 집계)
              ─→ SessionTurn.cost_event_id

SessionTurn   ─→ Card (citations 역참조)
              ─→ RawChunk (citations 역참조)

ProfileFactExtended.validation_history
  ──sidecar──→ fact_history/<fact_id>.jsonl

DecisionPatternExtended.outcome_history
  ──sidecar──→ pattern_history/<pattern_id>.jsonl
```
