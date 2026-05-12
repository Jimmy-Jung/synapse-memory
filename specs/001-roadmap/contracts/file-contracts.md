# File Contracts — Roadmap v0.5 → v0.8

본 문서는 신규 jsonl·markdown 파일의 정확한 schema 와 경로/권한/회전 정책을 정의한다. `data-model.md` 의 dataclass 와 1:1 매핑되며, 본 contract 는 *디스크 표현* 의 진실원본이다.

## 표기

- 경로의 `~` 는 사용자 home, `<vault>` 는 `$SYNAPSE_OBSIDIAN_VAULT`.
- 모든 jsonl 은 line-delimited JSON (RFC 7464 변형, 줄바꿈 `\n`).
- 파일 권한: L0 jsonl 은 `0600`, 디렉터리는 `0700`.

---

## F1. `~/.synapse/private/feedback.jsonl`

### Schema (1줄/event)

```json
{
  "event_id": "01HZX5V3F8GQ4J1Z9D2M0N4P5R",
  "ts": "2026-05-12T14:23:55Z",
  "target_kind": "card",
  "target_ref": "dansim-ios",
  "action": "reject",
  "weight": -0.30,
  "reason": "<redacted reason>",
  "answer_id_context": "01HZX5V3F8GQ4J1Z9D2M0N4P59"
}
```

### 정책
- append-only. mutate 금지.
- 손상 라인은 시작부터 첫 실패 지점까지 보존하고, 해당 라인부터 EOF 를 `.bak` 으로 옮긴 뒤 새 파일 시작 (B1).
- 회전 없음 (event ID 가 ULID 이므로 시계열로 자연 정렬).

### 적용 시점
- 다음 `daily index` 단계에서 `feedback/apply.py` 가 집계 → ChromaDB metadata 의 `feedback_score` 필드로 반영 (R2).

---

## F2. `~/.synapse/private/cost.jsonl`

### Schema (1줄/event)

```json
{
  "event_id": "01HZX5V3F8GQ4J1Z9D2M0N4P5T",
  "ts": "2026-05-12T14:23:55Z",
  "command": "me decide",
  "model": "claude-opus-4-7",
  "input_tokens": 1234,
  "output_tokens": 456,
  "usd": 0.0089,
  "elapsed_s": 4.21,
  "exit_code": 0,
  "error_class": null
}
```

### 정책
- append-only.
- 연간 회전: 매년 1월 1일 첫 호출 시, 전년도 파일을 `cost.YYYY.jsonl` 로 rename (예: `cost.2026.jsonl`).
- 단가표 미존재 모델: `usd: null`. `cost summary` 가 "N/A" 로 표시.

### 생성자
- `llm/apfel.py:complete()` 와 `llm/claude.py:complete()` 가 호출 완료 시 finally block 에서 emit.
- 예외 발생 시도 emit (input_tokens 만 알려진 경우 output_tokens=0, exit_code=1).

---

## F3. `~/.synapse/private/sessions/<session_id>.jsonl`

### Schema (1줄/turn)

```json
{
  "turn_idx": 0,
  "ts": "2026-05-12T14:23:55Z",
  "role": "user",
  "text": "<redacted user query>",
  "citations": [],
  "cost_event_id": null
}
```

### 정책
- `session_id` 는 ULID (사용자가 지정 가능, 기본 자동 생성).
- 50턴 또는 1MB 초과 시 회전: `<session_id>.001.jsonl`, `<session_id>.002.jsonl`, ... (data-model.md §"회전 정책").
- assistant turn 의 `citations` 는 card_id 또는 chunk_id 의 리스트.

### 마지막 답변 추적
- `endpoints/session.py` 가 매 응답마다 `~/.synapse/private/last_response.json` 을 갱신:

```json
{
  "answer_id": "01HZX5V3F8GQ4J1Z9D2M0N4P59",
  "session_id": "01HZX5V3F8GQ4J1Z9D2M0N4P50",
  "turn_idx": 1,
  "citations": ["dansim-ios", "raw_obsidian:abc123:5"],
  "ts": "2026-05-12T14:23:55Z"
}
```

- `feedback last` 는 본 파일을 참조하여 `target_ref` 를 채운다.

---

## F4. `<vault>/90_System/AI/DailyReports/YYYY-MM-DD.md`

`data-model.md §3 DailyReport` 의 YAML frontmatter + 본문(단계별 표).

### 본문 템플릿

```markdown
# Daily Report — 2026-05-12

| Stage | Status | Elapsed | Summary |
|---|---|---|---|
| collect_claude_code | ok | 0.0s | 변경 없음 |
| collect_obsidian | ok | 0.2s | scanned=1356 mirrored=3 |
| classify | ok | 0.8s | 신규 cluster 없음 |
| generate | ok | 18.7s | 신규 Card 1개 |
| index | ok | 26.5s | project=11 company=2 |
| update_profile | ok | 47.6s | fact=15 → MemoryInbox PR |

## Cost
- Claude: $0.42 (input 12,340 → output 4,560 tokens)
- apfel: 0 USD (로컬)

## 다음 검토 후보
- MemoryInbox/Profile-2026-05-12.md (15 facts)
```

### 정책
- 같은 날 두 번째 `daily` 실행 시 기존 파일 **append** (재시도 기록 보존): `## Re-run at HH:MM` 헤더 추가.
- 헌법 원칙 V (Observability) 의 영구 기록 요건 충족.

---

## F5. `~/.synapse/private/.tokens/<service>.json`

### Schema (Gmail 예시)

```json
{
  "service": "gmail",
  "scope": "https://www.googleapis.com/auth/gmail.readonly",
  "refresh_token": "<redacted>",
  "client_id": "<from .env or config>",
  "client_secret_path": "~/.synapse/private/.tokens/gmail-secret.json",
  "created": "2026-05-12T14:23:55Z",
  "last_refreshed": "2026-05-12T14:23:55Z"
}
```

### 정책
- 권한 `0600`. 디렉터리 `.tokens/` 는 `0700`.
- access token 은 디스크 저장 X (메모리만 유지).
- `doctor` 가 각 토큰의 만료/스코프 검증 후 결과 보고.

---

## F6. `~/.synapse/private/profile/fact_history/<fact_id>.jsonl`

ProfileFactExtended.validation_history 의 sidecar (R-B2).

```json
{
  "ts": "2026-05-12T14:23:55Z",
  "delta": 0.05,
  "reason": "user accepted decide outcome",
  "source_event_id": "01HZX5V3F8GQ4J1Z9D2M0N4P5R"
}
```

회전 없음. `fact_id` 가 삭제되면 sidecar 도 함께 삭제(또는 `.removed` 폴더 이동).

---

## F7. `~/.synapse/private/profile/pattern_history/<pattern_id>.jsonl`

DecisionPatternExtended.outcome_history sidecar.

```json
{
  "ts": "2026-05-12T14:23:55Z",
  "outcome": "good",
  "decision_ref": "session=01HZ... turn=3",
  "delta_applied": 0.05
}
```

---

## F8. ChromaDB collections

### `cards` (기존)
- ID: `{source_kind}:{card_id}` (예: `card_project:dansim-ios`)
- Metadata: `source_kind, card_id, display_name, status, domains, stack, period_start, period_end, last_reviewed, feedback_score`
- 신규 metadata: `feedback_score: float` (기본 1.0)

### `chunks` (신규, FR-B1)
- ID: `{source_kind}:{path_hash}:{chunk_index}`
- Metadata: `source_kind ∈ {raw_obsidian, raw_claude_code}, path, chunk_index, created`
- text 본문은 ChromaDB `documents` 필드에 저장.

### `bm25_index` (신규, FR-B2)
- ChromaDB 외부, `~/.synapse/private/rag/bm25/` 에 pickle. bge-m3 dense 결과와 RRF(k=60) 결합.

---

## 권한 / 디렉터리 트리

```
~/.synapse/                              0700
├── private/                             0700
│   ├── raw/                             0700
│   ├── redacted/                        0700
│   ├── rag/
│   │   ├── chroma/                      0700
│   │   └── bm25/                        0700  (신규)
│   ├── sessions/                        0700  (신규)
│   │   └── <id>.jsonl                   0600
│   ├── profile/
│   │   ├── fact_history/                0700  (신규)
│   │   └── pattern_history/             0700  (신규)
│   ├── .tokens/                         0700  (신규)
│   │   └── *.json                       0600
│   ├── logs/                            0700  (신규, launchd 출력)
│   ├── feedback.jsonl                   0600  (신규)
│   ├── cost.jsonl                       0600  (신규)
│   └── last_response.json               0600  (신규)
└── cache/                               0700
    └── whisper/                         0700  (신규, 모델 weights)
```

`doctor` 는 위 트리의 모든 디렉터리 권한을 검증하고, 어긋난 경우 자동 수정 + WARN 출력 (헌법 원칙 I).
