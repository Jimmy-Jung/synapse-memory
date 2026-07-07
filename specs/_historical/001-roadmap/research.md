# Phase 0 — Research

본 research 는 spec 의 미해결 결정 7개와 신규 의존성 5개에 대한 사전 조사를 정리한다. 코드 레벨 결정은 각 Phase 의 자체 plan 에서 확정하되, **본 문서가 가이드라인** 을 제공한다.

## R1. Timeline 정렬 — 어떤 필드를 사용할까

- **Decision**: `period_end desc` 1차, 동률 시 `created desc` 2차. ProjectCard 에 `period_end` 가 없으면(`status=active`) `today` 로 폴백.
- **Rationale**: 사용자가 회상할 때 "기억이 끝난 시점" 이 가장 직관적. `created` 는 Card 생성 시점이지 사건 시점이 아니라 부정확. CompanyCard 는 `period` 가 없으므로 `last_reviewed` 사용.
- **Alternatives considered**:
  - `last_reviewed` 단독: Card 를 자주 편집하면 시간순이 뒤섞임. 기각.
  - `period_start asc`: 시작 시점부터 이야기하는 모드도 유용하나 P1 범위 외. `--timeline-asc` 옵션으로 v0.6+ 검토.

## R2. Feedback weight → 인덱싱 적용 방식

- **Decision**: `feedback/apply.py` 가 `feedback.jsonl` 의 `target_kind=card` event 를 집계하여 카드별 `feedback_score ∈ [0.5, 1.5]` 로 정규화 → indexing 시 vector 의 metadata 에 저장 → retrieve 후 `score *= feedback_score` 곱셈 보정.
- **Rationale**: ChromaDB 의 score 후처리 hook 이 없으므로, retrieve 후 client-side 보정이 가장 단순. 정규화 범위 [0.5, 1.5] 는 한 번의 reject 가 영구 차단되지 않게 함.
- **Alternatives**:
  - 인덱싱 시점에 embedding 재가중: 비용 큼. 기각.
  - 별도 reranker: 의존성 큼 (cross-encoder). 추후 검토.

## R3. Cost 추정 — Anthropic 토큰 단가

- **Decision**: 모델별 단가 테이블을 `src/synapse_memory/cost/pricing.py` 에 하드코딩(단, 출처 주석 + 마지막 갱신일). 알 수 없는 모델은 `usd=null` 저장 후 summary 에서 "N/A" 표시.
- **Rationale**: 외부 API call 로 가격 조회는 부담 + 로컬 추정 정확도 ±10% 충분 (SC-003). 모델 출시 시 PR 로 가격 추가하는 운영 정책.
- **Alternatives**:
  - 사용자가 매월 청구액 입력 → 역산: UX 부담. 기각.

## R4. BM25 — 어떤 토크나이저?

- **Decision**: `rank-bm25==0.2.2` + 자체 한국어 친화 토크나이저 (whitespace + 영문 punctuation + 한글 음절 그대로). 형태소 분석기 불필요.
- **Rationale**: 회사명·사람 이름 같은 고유명사는 음절 단위로도 충분히 매칭됨. KoNLPy/mecab 추가 시 macOS 빌드 부담 큼.
- **Alternatives**:
  - mecab: 의존성·빌드 복잡. 기각.
  - whoosh: 인덱스 영속화가 필요하나 ChromaDB 와 이원화. 기각.
- **Test**: golden 20건 (한국 회사명/사람 이름 절반 포함) 에서 SC-007 달성 검증.

## R5. Whisper — 로컬 음성 인식 모델

- **Decision**: `faster-whisper` (CTranslate2 백엔드) + `large-v3` 모델 weights. Apple Silicon GPU(MPS) 활용 가능, 30분 음성 ≈ 1분 처리.
- **Rationale**: 로컬 실행 (헌법 원칙 I), 정확도 우수, 단일 binary 의존성.
- **Alternatives**:
  - `whisper.cpp`: C++ 빌드 부담. 기각.
  - OpenAI Whisper API: 외부 송신 → 헌법 원칙 I 위반. 기각.
- **위험**: 모델 weights ~3GB. `~/.synapse/cache/whisper/` 에 보관, gitignore.

## R6. Gmail 수집 — OAuth 권한

- **Decision**: `https://www.googleapis.com/auth/gmail.readonly` scope + `oauth2client` 대신 modern `google-auth-oauthlib` 사용. 로컬 호스트 콜백(`http://localhost:8765`) 으로 토큰 발급, refresh token 만 `.tokens/gmail.json` 0600 보관.
- **Rationale**: read-only 로 부수효과 차단. 로컬 콜백은 redirect URI 등록만으로 가능.
- **Alternatives**:
  - Gmail IMAP + App password: 2FA 환경에서 추가 단계. 기각.
  - Service Account: 개인 계정에는 부적합. 기각.

## R7. iMessage 수집 — chat.db 접근

- **Decision**: macOS Full Disk Access 권한 + `sqlite3.connect("~/Library/Messages/chat.db", uri=True, mode='ro')` 로 read-only.
- **Rationale**: 가장 단순. Apple 이 정식 API 미제공.
- **Risk**: macOS major 업데이트 시 스키마 변경 가능. CI 에서 fixture chat.db 로 회귀 테스트.
- **Alternatives**:
  - iMazing 등 export 도구 결과 파싱: 사용자 추가 도구 의존. 기각.

---

## 베스트 프랙티스

### B1. jsonl append-only 안전성
- 모든 jsonl writer 는 `O_APPEND | O_CREAT` + `os.fsync` + 1줄 = 1 JSON object.
- 손상 복구: 파일 시작부터 `json.loads` 실패하는 라인은 `<file>.bak` 로 옮기고 skip. `doctor` 에서 보고.

### B2. ChromaDB metadata 한도
- ChromaDB metadata 값은 str/int/float/bool 만 허용. 리스트는 `,` join. 본 plan 의 `validation_history` 등 list 필드는 별도 sidecar jsonl 로 분리 저장.

### B3. macOS LaunchAgent
- `~/Library/LaunchAgents/com.synapse.daily.plist` — `StartCalendarInterval` 로 매일 새벽 5시. `StandardOutPath` / `StandardErrorPath` 를 `~/.synapse/private/logs/launchd.{out,err}.log` 로. `docs/operations.md` 에 템플릿.

### B4. 헌법 §"Spec Kit flow" — 각 Phase PR 검사 체크리스트
- redaction eval golden 실행 결과 첨부 (Pass1·Pass2 F1)
- `daily --dry-run` 출력 첨부 (idempotence 확인)
- 신규 endpoint 의 interactive/batch 분류 PR description 명시
- cost.jsonl 1 row 샘플 첨부 (FR-A3 도입 후)

### B5. Slash 명령 markdown 템플릿
- 신규 슬래시 명령(예: `commands/synapse-feedback.md`) 은 다음 헤더 포함:
  ```markdown
  ---
  description: 사용자 피드백 기록 — 마지막 답변 거절 / 패턴 가중치 조정
  ---
  Run `SYNAPSE_FROM_AGENT=1 synapse-memory feedback ...`
  ```
- `SYNAPSE_FROM_AGENT=1` 누락 시 CI 에서 정적 검사로 거부 (FR-X1).

---

## 미해결 결정 ↔ Phase 매핑

| Phase | 결정 | 본 research 참조 |
|---|---|---|
| 002-timeline-recall | period_end vs created | R1 |
| 003-feedback-loop | weight 적용 시점 | R2 |
| 004-cost-observability | 토큰 단가 출처 | R3 |
| 006-raw-rag-hybrid | 토크나이저 | R4 |
| 012-collector-gmail | OAuth scope | R6 |
| 010-collector-imessage | sqlite read-only | R7 |
| 013-collector-voice | Whisper 변형 | R5 |
