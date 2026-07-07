# CLI Contracts — Roadmap v0.5 → v0.8

본 contract 는 신규/수정되는 CLI 명령의 인터페이스를 정의한다. 각 명령은 (1) 호출 형태, (2) interactive/batch 분류 (헌법 원칙 IV), (3) exit code 정책, (4) `SYNAPSE_FROM_AGENT` 가드 동작 을 명시한다.

## 표기

- 모든 명령은 `synapse-memory` console script 의 서브커맨드.
- `[arg]` = 선택, `<arg>` = 필수.
- Exit code: `0` = success, `1` = recoverable error, `2` = config/permission error, `3` = redaction/security violation.

---

## v0.5 — Phase A

### `me what-did-i-think <topic> [--timeline] [--by {time|distance}] [--limit N]`

- **분류**: 대화형 (헌법 IV)
- **가드**: TTY 직접 호출 시 3초 안내 → `SYNAPSE_FROM_AGENT=1` 자동 통과
- **--timeline**: 결과를 `period_end desc`(R1)로 재정렬, 월/분기/연도 헤더 출력
- **--by time**: 시간 단독 정렬, `--by distance`: 기존 cosine 만
- **출력**: stdout markdown — 그룹별 표 또는 timeline view
- **Exit**: 0 (결과 0건 포함, 빈 timeline 안내)

### `synapse-memory feedback <subcommand> [args]`

- **분류**: 배치 (자동화 가능, TTY 안내 없음)
- **서브커맨드**:
  - `last --reject <reason> | --accept | --weight <delta>` — 직전 ask/me 답변에 대한 피드백
  - `pattern <pattern_id> --weight <delta>` — DecisionPattern 가중치 조정
  - `card <card_id> --reject <reason> | --accept` — 특정 Card 의 검색 가중치 조정
- **부작용**: `~/.synapse/private/feedback.jsonl` append, `last_response.json` 참조하여 target_ref 채움
- **Exit**: 0 / 1 (last_response.json 없음 등) / 2 (jsonl 권한 오류)

### `synapse-memory cost summary [--days N] [--by {command|model}] [--json]`

- **분류**: 배치
- **--days**: 기본 30
- **--by command** (기본): command 별 합계
- **--json**: 표 대신 JSON dump
- **Exit**: 0 / 1 (cost.jsonl 없음 — "데이터 없음" 출력 후 0)

### `synapse-memory daily [--dry-run] [--resume-from <stage>] [--profile-facts-only]`

- **분류**: 배치 (변경 없음)
- **신규 옵션** `--resume-from <stage>`: 지정 stage 부터 실행. stage 이름은 `collect_claude_code | collect_obsidian | classify | generate | index | update_profile | report` 중 하나.
- **신규 동작**: 한 stage 실패 시 의존 stage 는 SKIP 마크. 종료 시 vault `DailyReports/YYYY-MM-DD.md` 작성.
- **Exit**: 0 (모든 stage ok) / 1 (한 stage 이상 failed)

---

## v0.6 — Phase B

### `synapse-memory rag index [--include-raw] [--card-only] [--rebuild]`

- **분류**: 배치
- **--include-raw**: RawChunk 인덱싱 활성화. vault `10_Active/*` + L1 redacted/claude-code/* chunk(512 token, 64 overlap)
- **--rebuild**: 전체 인덱스 재구축 (vector DB drop & insert)
- **Exit**: 0 / 1

### `synapse-memory ask <query> [--hybrid] [--preview-prompt] [--session <id>] [--limit N]`

- **분류**: 대화형
- **--hybrid**: dense + BM25 RRF 결합 (R4)
- **--preview-prompt**: Claude 호출 직전 redacted prompt 를 stdout 출력 후 enter 대기. `SYNAPSE_FROM_AGENT=1` 환경에서 무시.
- **--session <id>**: multi-turn 컨텍스트 로드/저장 (v0.8 의 FR-D5 — v0.6 stub 으로 인터페이스만 노출, 실동작은 v0.8)
- **Exit**: 0 / 3 (redacted 결과가 0바이트, 외부 송신 차단)

### `synapse-memory me draft-reply <message> [--preview-prompt] [--profile-voice]`

- **분류**: 대화형
- **출력 파일**: `<vault>/30_Creative/Drafts/Reply - YYYY-MM-DD.md`
- **Exit**: 0 / 1 (Profile.md 없음 — 경고 후 voice 미적용으로 진행)

### `synapse-memory card update <card_id> [--auto-apply] [--dry-run]`

- **분류**: 배치
- **--auto-apply**: 사용자 검토 없이 "## Proposed additions" 섹션을 본문에 머지 (위험, 기본 OFF)
- **출력**: stdout 에 unified diff
- **Exit**: 0 / 1

---

## v0.7 — Phase C

### `synapse-memory collect imessage [--db <path>] [--since <date>]`

- **분류**: 배치
- **권한**: macOS Full Disk Access 필요. 미부여 시 exit 2 + 안내 메시지
- **--db**: 기본 `~/Library/Messages/chat.db`, 사용자 지정 export 가능
- **--since**: 기본 마지막 mirror 이후 (incremental)
- **Exit**: 0 / 1 / 2

### `synapse-memory collect kakaotalk --path <txt> [--since <date>]`

- **분류**: 배치
- **요구**: KakaoTalk 가 export 한 .txt 파일 경로
- **Exit**: 0 / 1

### `synapse-memory collect gmail [--label <name>] [--max N] [--reauth]`

- **분류**: 배치 (단, `--reauth` 시 첫 호출은 브라우저 콜백 필요)
- **OAuth**: 첫 호출 시 `http://localhost:8765` 콜백, refresh token 만 `.tokens/gmail.json` 0600 저장 (R6)
- **--label**: 기본 `synapse/inbox`
- **--max**: 한 번 호출에 처리할 최대 메일 수 (기본 200)
- **Exit**: 0 / 1 / 2 (OAuth 만료 — 재인증 안내)

### `synapse-memory collect voice [--source <dir>] [--model <name>]`

- **분류**: 배치
- **--source**: 기본 `~/Documents/VoiceMemos`
- **--model**: 기본 `large-v3` (faster-whisper)
- **첫 호출**: 모델 weights 다운로드 (`~/.synapse/cache/whisper/`), 진행률 표시
- **Exit**: 0 / 1 / 2

---

## v0.8+ — Phase D

### `synapse-memory me decide <situation> [--outcome {good|bad}] [--session <id>] [--preview-prompt]`

- **분류**: 대화형
- **--outcome**: 직전 24h 결정에 대한 사후 평가. `~/.synapse/private/feedback.jsonl` 에 `target_kind=pattern` 이벤트 추가
- **Exit**: 0 / 1

### `synapse-memory me update-profile [--auto-promote] [--min-confidence X] [--detect-conflicts]`

- **분류**: 배치
- **--detect-conflicts** (신규, FR-D3): 모순 ProfileFact 쌍 검출 후 MemoryInbox 에 "## Conflicts" 섹션 추가
- **--auto-promote** (기존 backlog): 신뢰도 ≥ min-confidence 인 fact 를 자동 승격, `auto_promoted: true` 마킹
- **Exit**: 0 / 1

### `synapse-memory eval calibration [--golden <path>]`

- **분류**: 배치
- **--golden**: 기본 `tests/golden/calibration_30.jsonl` (gitignore)
- **출력**: follow-rate, NDCG@5, 카드별 break-down
- **Exit**: 0 / 1

---

## 공통 규칙

### 인터랙티브 가드 (FR-X1)

대화형 분류 명령은 모두 `cli._interactive_guard()` 진입:

```
TTY + stdout 가 터미널 → 3초 안내 → 진행
SYNAPSE_FROM_AGENT=1     → 즉시 통과
stdout 가 파이프         → 즉시 통과
```

### Slash 명령 markdown (B5)

신규 슬래시 명령(예: `commands/synapse-feedback.md`) 추가 시 다음 헤더 필수:

```markdown
---
description: <한 줄 설명>
---
Run `SYNAPSE_FROM_AGENT=1 synapse-memory <subcommand> $ARGUMENTS`
```

`SYNAPSE_FROM_AGENT=1` 누락은 CI 정적 검사로 실패시킨다.

### Redaction 게이트 (FR-X2)

외부 LLM 으로 흐르는 모든 텍스트(Claude wrapper `complete()` 의 prompt) 는 진입 전 `redact_full()` 호출 흔적이 PR diff 에 보여야 한다. 명령 별 책임 위치:

| 명령 | redact 책임 위치 |
|---|---|
| `ask`, `me *` | `endpoints/{ask,me}.py:_build_prompt()` |
| `card generate`, `card update` | `cards/{auto_generate,update}.py` |
| `me update-profile` | `profile/extract.py` (기존, 변경 없음) |

### `--preview-prompt` (FR-B3, Pass 3)

대화형 명령의 공통 옵션. `SYNAPSE_FROM_AGENT=1` 에서는 silently 비활성. stdout 출력 포맷:

```
─── PREVIEW: about to send to claude-opus-4-7 (input ≈ 1234 tokens, est $0.0089) ───
<redacted prompt full text>
─── End preview. Press Enter to send, Ctrl+C to abort. ───
```
