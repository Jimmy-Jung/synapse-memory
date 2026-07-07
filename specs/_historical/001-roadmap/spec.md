# Feature Specification: Roadmap v0.5 → v0.8 (Synapse Memory Meta-Plan)

**Feature Branch**: `001-roadmap`
**Created**: 2026-05-12
**Status**: Draft
**Input**: User description: "로드맵 전부 구현 계획" (참조: `docs/assessment-2026-05-12.md`)

## User Scenarios & Testing *(mandatory)*

본 meta-feature 의 "사용자"는 도구 소유자(Synapse Memory Maintainers) 본인이며, 시스템이 매일·매주·매월 단위로 더 똑똑해지는 경험이 핵심 가치다. 각 User Story 는 **하나의 마일스톤(v0.5~v0.8)** 에 대응하고, 독립 출시 가능하도록 슬라이스되어 있다. P1 단독 출시만으로도 사용자에게 의미 있는 가치 (`me what-did-i-think` 가 시간순으로 동작 + 비용 가시화) 가 도달한다.

### User Story 1 — v0.5 "쓰면 더 똑똑해지는 도구" (Priority: P1)

매일 도구를 쓰는 사용자가 (1) 과거 생각을 *시간순으로* 회상하고, (2) 잘못된 추천에 피드백을 남기고, (3) 어제 도구가 얼마 썼는지 확인하고, (4) daily 파이프라인이 실패해도 안전하게 재개할 수 있어야 한다.

**Why this priority**: 평가 리포트(`docs/assessment-2026-05-12.md`)가 지적한 두 핵심 결함(W1 시간축 회상 부재, W2 Feedback 루프 부재)을 해소해야 "세컨드 브레인" 정체성이 회복된다. v0.5 단독으로도 사용자 일상 가치가 즉시 향상된다.

**Independent Test**: 새 macOS 워크스테이션에서 `synapse-memory daily` → `synapse-memory me what-did-i-think 클린아키텍처 --timeline` → `synapse-memory feedback last --reject "관련 없음"` → `synapse-memory cost summary --days 30` 4개를 순차 실행하면 (a) 회상이 월별 시간순 정렬되어 출력되고 (b) feedback.jsonl 에 1줄이 append 되고 (c) cost 요약이 출력되며 (d) `90_System/AI/DailyReports/2026-05-12.md` 가 vault 에 생성된다.

**Acceptance Scenarios**:

1. **Given** vault 에 6개월 이상에 걸친 ProjectCard 가 존재, **When** `me what-did-i-think <topic> --timeline` 실행, **Then** 결과가 `period_start` 내림차순으로 정렬되고 월별 그룹 헤더가 출력된다.
2. **Given** 직전 `ask` 답변이 마음에 들지 않는다, **When** `synapse-memory feedback last --reject "<이유>"` 실행, **Then** `~/.synapse/private/feedback.jsonl` 에 1줄 append 되고 해당 답변의 인용 카드들의 confidence 가 다음 인덱싱에서 0.85× 가중된다.
3. **Given** Claude/apfel 호출이 어제 5번 일어났다, **When** `cost summary --days 1` 실행, **Then** command 별 총 토큰·예상 USD·평균 elapsed 가 표로 출력된다.
4. **Given** `daily` 의 classify 단계가 apfel timeout 으로 실패, **When** `daily` 가 종료, **Then** generate 단계는 SKIP(required_for 의존성) 으로 마크되고 종료 코드는 1 이며 `daily --resume-from classify` 가 재시도를 처음부터 보장한다.
5. **Given** push 가 main 으로 발생, **When** GitHub Actions 가 실행, **Then** pytest + ruff + mypy 모두 green 이어야 PR 머지 가능하다.

---

### User Story 2 — v0.6 "맥락 폭 확장" (Priority: P2)

Card 에 아직 반영되지 않은 raw 노트도 검색되고, 고유명사 검색 정확도가 회사명·사람 이름에서 눈에 띄게 개선되며, 외부 LLM 전송 직전 redacted 결과를 한 번 확인할 수 있어야 한다. 답장 초안과 Card incremental update 도 제공한다.

**Why this priority**: v0.5 가 회상·학습 신호의 토대를 만든 뒤, 그 위에서 검색 품질(W3, W10) 과 안전망(W5) 을 끌어올린다. 단독 출시 가능 — v0.5 의 시간축 회상에 raw chunk 추가만 켜져도 의미 있는 정확도 향상.

**Independent Test**: `synapse-memory rag index --include-raw` 후 `synapse-memory ask "특정 인물 이름"` 실행 시 (a) Card 와 raw chunk 가 함께 인용되고 (b) BM25 점수가 보조 표시되며 (c) `--preview-prompt` 옵션으로 Claude 에 보낼 최종 텍스트가 stdout 으로 먼저 출력된다.

**Acceptance Scenarios**:

1. **Given** vault `10_Active/<note>.md` 가 Card 화되지 않은 채 존재, **When** `rag index --include-raw` 후 `ask <키워드>`, **Then** raw chunk 가 인용 결과에 표시되고 source_kind 가 `raw_obsidian` 으로 표기된다.
2. **Given** 검색어가 한국 회사명(예: "샘플회사B"), **When** `ask --hybrid`, **Then** dense + BM25 결과가 RRF 로 결합되어 keyword 매칭 카드가 상위에 표시된다.
3. **Given** `me decide` 호출 직전, **When** `--preview-prompt` 옵션, **Then** Claude 로 보낼 최종 텍스트(redacted 후)가 stdout 출력되고 확인 입력 전까지 호출 대기 (단, `SYNAPSE_FROM_AGENT=1` 환경에서는 자동 통과).
4. **Given** 받은 메시지 "내일 회의 가능?", **When** `me draft-reply "<메시지>"`, **Then** 30_Creative/Drafts/Reply-YYYY-MM-DD.md 가 생성되며 Profile voice 와 관련 Card 기반.
5. **Given** ProjectCard `sample-ios-app` 가 이미 존재하고 사용자 본문이 있음, **When** `card update sample-ios-app`, **Then** 사용자 본문은 보존되고 새 raw 에서 발견한 메트릭만 "## Proposed additions" 섹션에 draft 로 추가된다.

---

### User Story 3 — v0.7 "맥락 입력 채널 확장" (Priority: P3)

업무·생활 맥락이 Obsidian 과 Claude Code 두 채널을 넘어 메신저·메일·음성·브라우저까지 확장된다.

**Why this priority**: v0.5~v0.6 가 도구의 *깊이*를 만든 뒤, v0.7 은 *너비*를 채운다. 사용자 데이터 풍부도가 클론 정확도 마일스톤(v0.8) 의 전제조건이라서 D 보다 먼저.

**Independent Test**: 각 collector 는 독립적으로 켤 수 있어야 한다 — 예: iMessage 만 활성화한 상태에서 `collect imessage` → L0 에 mirror → redact → cluster 까지 daily 통합 단계가 정상 동작.

**Acceptance Scenarios**:

1. **Given** iMessage export(`chat.db` 백업 또는 export 스크립트) 가 존재, **When** `collect imessage`, **Then** L0 에 mirror 되고 `0700` 권한이 유지되며 incremental 동작한다.
2. **Given** KakaoTalk 채팅 export(.txt), **When** `collect kakaotalk --path <file>`, **Then** L0 저장 + Pass1 마스킹 후 cluster scan 에 포함된다.
3. **Given** Gmail label `synapse/inbox` 의 메일, **When** `collect gmail`, **Then** OAuth 토큰은 `~/.synapse/private/.tokens` 에 0600 으로 저장되며 redacted 본문만 외부 LLM 으로 흐른다.
4. **Given** macOS 음성 메모(`.m4a`), **When** `collect voice`, **Then** Whisper(로컬) 로 transcribe 된 텍스트가 L0 저장 후 redact 파이프라인을 탄다.

---

### User Story 4 — v0.8+ "클론 정확도" (Priority: P3)

`me decide` 가 사용자의 결정 결과를 학습하고, 오래된 패턴을 자동 감쇠하며, 모순된 ProfileFact 를 경고하고, 멀티턴 대화 컨텍스트를 유지한다.

**Why this priority**: v0.5 의 feedback 루프, v0.6 의 raw RAG, v0.7 의 데이터 폭이 모두 갖춰진 뒤에야 의미 있는 calibration / decay 가 가능. 잘못된 순서로 진입하면 잘못된 데이터로 잘못된 클론을 학습.

**Independent Test**: 골든셋 30건 결정 시나리오에서 v0.8 적용 전/후 calibration ratio(사용자가 따른 비율) 가 측정 가능해야 한다.

**Acceptance Scenarios**:

1. **Given** ProfileFact A 와 B 가 모순(예: "리스크 회피적" vs "공격적 투자 선호"), **When** `me update-profile`, **Then** 충돌 경고가 MemoryInbox 에 별도 섹션으로 출력된다.
2. **Given** DecisionPattern 의 `extracted_at` 이 365일 이상 경과, **When** 다음 인덱싱, **Then** confidence × decay_factor (예: 0.7) 가 적용된다.
3. **Given** `me decide --outcome good` 가 결정 후 24시간 이내 호출, **When** 다음 daily, **Then** 관련 패턴의 confidence 가 +0.05 보정된다.
4. **Given** `ask` 답변 직후 follow-up, **When** `synapse-memory ask --session <id> "<후속 질문>"`, **Then** 이전 컨텍스트가 유지된 답변이 반환된다 (세션 jsonl `~/.synapse/private/sessions/<id>.jsonl`).

---

### User Story 5 — Interface 확장 (Priority: P4, 병행 가능)

macOS menubar, iOS Shortcuts, Obsidian plugin 등 인터페이스 채널을 늘려 도구 접근성을 높인다. 본 마일스톤은 v0.5~v0.8 의존성이 적어 병행 가능.

**Why this priority**: 핵심 가치는 v0.5~v0.8 에 있다. Interface 는 채택률을 높이지만 도구의 가치 자체를 결정하지 않는다.

**Independent Test**: menubar app 단독으로 `daily` 결과 알림과 `ask` 핫키가 동작해야 한다.

**Acceptance Scenarios**:

1. **Given** menubar app 설치, **When** daily 종료, **Then** 새 Card 수·실패 단계가 macOS 알림으로 표시된다.
2. **Given** Obsidian plugin 활성, **When** 노트에서 우클릭 "관련 카드 보기", **Then** 패널에 RAG 결과가 표시된다.

---

### Edge Cases

- **apfel 미설치 / macOS 25 이하**: Pass 2 가 동작 불가 → `doctor` 가 ERROR 종료, daily 진입 차단 (헌법 원칙 I).
- **redacted 결과가 0바이트 (모든 토큰이 PII)**: 외부 LLM 호출 차단하고 "전송 가능 콘텐츠 없음" 경고.
- **feedback.jsonl 손상**: 다음 부팅 시 자동 backup `feedback.jsonl.bak` 생성 + 빈 파일로 복구.
- **세션 jsonl 비대**: 세션 1개당 50턴 또는 1MB 초과 시 자동 회전(`<id>.001.jsonl`).
- **iCloud 동기화로 0700 chmod 실패**: 현재 silent OSError catch 유지하되, `doctor` 가 명시적 WARN 출력.
- **cost.jsonl 미존재시 첫 호출**: append 모드로 자동 생성, 헤더 라인 없음.
- **timeline 회상 결과 0건**: distance 만 사용한 결과로 자동 fallback + "시간 정보 없음" 라벨.
- **collector 1개 실패 (예: gmail OAuth 만료)**: 다른 collector 와 격리 — `daily` 가 해당 collector 만 SKIP 처리.

## Requirements *(mandatory)*

### Functional Requirements

#### v0.5 — P1 (Foundation)

- **FR-A1**: System MUST 제공 `me what-did-i-think <topic> --timeline` — 결과를 Card 의 `period_start desc` 또는 `created desc` 로 재정렬하고, 월/분기/연도 단위 그룹 헤더를 추가한다.
- **FR-A2**: System MUST 제공 `synapse-memory feedback {last|pattern|card} [--reject <reason>|--accept|--weight <delta>]` — 결과는 `~/.synapse/private/feedback.jsonl` 에 append-only 1줄 JSON 으로 기록된다.
- **FR-A3**: 모든 Claude / apfel 호출은 호출 종료 후 `~/.synapse/private/cost.jsonl` 에 `{ts, command, model, input_tokens, output_tokens, usd, elapsed_s}` 1줄을 append 한다.
- **FR-A4**: System MUST 제공 `synapse-memory cost summary [--days N] [--by command|model]` — JSON 또는 표로 집계 출력.
- **FR-A5**: `daily` 종료 시 `<vault>/90_System/AI/DailyReports/<YYYY-MM-DD>.md` 가 자동 생성. 포함: 단계별 elapsed, 새 Card 수, profile facts 후보 수, 실패 단계, 추정 USD.
- **FR-A6**: `daily` 의 각 stage 는 `required_for: list[str]` 메타를 가지며, 한 stage 실패 시 의존 stage 는 SKIP 상태로 마크하고 종료 코드 1 을 반환한다.
- **FR-A7**: `synapse-memory daily --resume-from <stage>` — 지정 stage 부터 재실행한다.
- **FR-A8**: `.github/workflows/ci.yml` 이 main / PR 에서 pytest + ruff + mypy 를 실행하며, apfel 및 Claude Code CLI 가 없는 환경에서도 mock 으로 통과해야 한다.
- **FR-A9**: Claude 답변에서 발생하는 "Insight:" 등 메타 프리픽스는 후처리에서 제거된다 (backlog.md P0).

#### v0.6 — P2 (Reach)

- **FR-B1**: `rag index --include-raw` 옵션 — vault `10_Active/`, `~/.synapse/private/redacted/claude-code/` 에서 chunk(512 token, 64 overlap) 단위 인덱싱. 메타 `source_kind=raw_obsidian | raw_claude_code`, `path`, `chunk_index`.
- **FR-B2**: `ask --hybrid`, `me what-did-i-think --hybrid` — dense 벡터 + BM25 결과를 RRF(k=60) 로 결합.
- **FR-B3**: 모든 사용자-대화형 endpoint 에 `--preview-prompt` 옵션 — 외부 LLM 호출 직전 redacted prompt 를 stdout 출력하고 사용자 enter 확인 후 진행. `SYNAPSE_FROM_AGENT=1` 에서는 비활성.
- **FR-B4**: `me draft-reply <메시지>` 명령 — Profile voice + 관련 Card 조회 후 `<vault>/30_Creative/Drafts/Reply-YYYY-MM-DD.md` 에 초안 저장.
- **FR-B5**: `card update <id>` — 기존 본문은 보존, 새 메트릭은 별도 "## Proposed additions" 섹션에 draft 로 추가. diff 가 stdout 으로 출력된다.

#### v0.7 — P3 (Breadth)

- **FR-C1**: `collect imessage [--db <path>]` — `~/Library/Messages/chat.db` (또는 사용자 지정 export) 에서 incremental mirror.
- **FR-C2**: `collect kakaotalk --path <txt>` — 사용자가 직접 export 한 .txt 를 L0 에 정규화 저장.
- **FR-C3**: `collect gmail [--label <name>]` — OAuth 토큰은 `~/.synapse/private/.tokens` (0600), 본문은 redact 후 외부 LLM 으로 흐른다.
- **FR-C4**: `collect voice [--source <dir>]` — `.m4a/.wav` 를 Whisper(로컬, faster-whisper) 로 transcribe 후 L0 저장.
- **FR-C5**: 각 collector 는 독립 실행 가능하고, daily 안에서 1개 실패해도 나머지 collector / stage 는 계속한다.

#### v0.8+ — P3 (Clone Accuracy)

- **FR-D1**: ProfileFact·DecisionPattern 에 `last_validated_at`, `validation_history: list[{ts, delta, reason}]` 필드 추가.
- **FR-D2**: 다음 인덱싱 시 `extracted_at` 이 N일(기본 365) 초과한 패턴은 confidence × decay_factor(기본 0.7) 적용. CLI flag 로 조정 가능.
- **FR-D3**: `me update-profile` 가 모순되는 ProfileFact 쌍을 자동 검출하여 MemoryInbox 에 "## Conflicts" 섹션 추가. 검출 알고리즘: 동일 category 내 동의어/반의어 쌍 매칭 (간단한 규칙 + apfel).
- **FR-D4**: `me decide --outcome {good|bad}` — 직전 24h 결정에 대한 사후 평가. 관련 패턴의 confidence 를 ±0.05 보정.
- **FR-D5**: `synapse-memory ask --session <id> "<후속>"` — 세션 jsonl(`~/.synapse/private/sessions/<id>.jsonl`) 에 multi-turn 컨텍스트 저장/로드.
- **FR-D6**: `eval calibration` — 골든셋 30건 시나리오에서 사용자가 추천을 따른 비율을 측정해 출력.

#### Interface (P4, 병행)

- **FR-E1**: macOS menubar app — daily 알림, `ask` 핫키, 비용 표시.
- **FR-E2**: Obsidian plugin — 노트 우클릭 → 관련 Card 패널, "이 노트로 Card 생성" 액션.
- **FR-E3**: iOS Shortcuts — 위젯에서 `/synapse-ask` 호출 (Tailscale/USB 경유, 외부 노출 없음).

### Cross-cutting Requirements

- **FR-X1**: 모든 신규 endpoint 는 `_interactive_guard()` 또는 `SYNAPSE_FROM_AGENT=1` bypass 정책을 헌법 원칙 IV 와 일치하도록 적용한다.
- **FR-X2**: 외부 LLM 으로 나가는 모든 payload 는 Pass 1+Pass 2 redaction 을 거친 텍스트여야 한다. 본 로드맵의 어떤 신규 기능도 raw 우회 경로를 만들지 않는다.
- **FR-X3**: 본 로드맵의 각 FR 은 머지 전 최소 1개 unit test 또는 integration test 가 추가되어야 한다 (헌법 원칙 III).
- **FR-X4**: redaction F1 회귀 한계: Pass1 ≥ 0.95, Pass2 ≥ 0.80. 위반 시 PR 차단(eval golden).

### Key Entities *(데이터 관련)*

- **FeedbackEvent**: `{event_id, ts, target_kind: "answer"|"pattern"|"card", target_ref, action: "accept"|"reject", weight: float, reason: str}`. `~/.synapse/private/feedback.jsonl` 에 1줄/event.
- **CostEvent**: `{ts, command, model, input_tokens, output_tokens, usd, elapsed_s, exit_code}`. `~/.synapse/private/cost.jsonl`.
- **DailyReport**: vault markdown — frontmatter `date, total_elapsed_s, errors_count, new_cards, new_facts, est_usd`, body 에 단계별 표.
- **SessionTurn**: `{turn_idx, ts, role: "user"|"assistant", text, citations: list[str], cost_event_id}`. `~/.synapse/private/sessions/<id>.jsonl`.
- **ProfileFactExtended**: 기존 + `last_validated_at, validation_history, conflicts_with: list[str]`.
- **DecisionPatternExtended**: 기존 + `last_validated_at, validation_history, decay_applied_at`.
- **RawChunk** (RAG): `{chunk_id, source_kind, path, chunk_index, text_redacted, embedding}`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (P1)**: `me what-did-i-think --timeline` 결과의 상위 10개가 시간순으로 정렬되어 있다 (Kendall τ ≥ 0.9 vs 기대 시간순 정렬). v0.5 출시 90일 내 사용자가 회상 명령을 주당 평균 3회 이상 사용한다.
- **SC-002 (P1)**: v0.5 출시 30일 내 사용자가 `feedback` 명령으로 10건 이상 신호를 남기고, 그 결과로 영향 받은 카드의 다음 인덱싱에서 confidence 가 실측 변화한다 (변화율 검증 테스트 통과).
- **SC-003 (P1)**: `cost summary --days 30` 의 USD 합계가 실제 Anthropic dashboard 청구액의 ±10% 이내.
- **SC-004 (P1)**: `daily` 중 한 stage 의 의도적 실패 주입(테스트) 시 의존 stage 가 SKIP 으로 표기되고, `--resume-from` 후 정상 회복까지 사용자 개입 < 1회.
- **SC-005 (P1)**: CI 가 push 마다 5분 내 완료되며 main 의 green 비율 ≥ 95% (월간).
- **SC-006 (P2)**: `--include-raw` 인덱싱 후 평가 셋 20개 질의에서 NDCG@5 가 Card-only 대비 ≥ +0.05 향상.
- **SC-007 (P2)**: `--hybrid` 옵션이 회사명·사람 이름 포함 질의 10건에서 top-1 정확도 ≥ +20%p.
- **SC-008 (P2)**: `--preview-prompt` 사용 시 redacted 결과에 사용자 정의 NDA 키워드가 1건도 leak 되지 않는다 (golden 30건 평가).
- **SC-009 (P3)**: 각 collector 가 단독 실행으로 100건 이상의 raw 항목을 24시간 내 안정적으로 mirror 한다.
- **SC-010 (P3)**: collector 1개 강제 실패 시 daily 의 다른 단계 영향 없음 (테스트로 검증).
- **SC-011 (P4)**: `eval calibration` 의 follow-rate (사용자가 추천을 따른 비율) 가 v0.7 베이스라인 대비 v0.8 에서 ≥ +15%p.
- **SC-012 (cross)**: 본 로드맵의 모든 PR 이 머지 시점에 ruff·mypy strict·pytest green.
- **SC-013 (cross)**: redaction F1 (Pass1 ≥ 0.95, Pass2 ≥ 0.80) 회귀 없음 (eval golden 매 PR 자동 실행).

## Assumptions

- Apple Silicon + macOS 26 (Tahoe) + Python 3.11+ 환경 유지 (헌법 원칙 § "Platform floor").
- apfel 과 Claude Code CLI 는 사용자 머신에서 OAuth 인증이 끝난 상태로 가정.
- vault 는 Obsidian iCloud 동기화 중이며 NFC 정규화 가정 (architecture.md §"Cluster 식별").
- 모든 collector 신규 추가는 raw → L0 → redact → cluster → card 표준 경로를 따른다. 우회 없음.
- 본 meta-spec 은 5개 Phase 의 *순서·의존성·게이트* 를 정의한다. 각 Phase 내 세부 사항은 별도 `/speckit-specify <기능>` 사이클에서 자체 spec 으로 확장한다 (`002-timeline-recall`, `003-feedback-loop`, `004-cost-observability` 등).
- v0.7 collector 추가 시 macOS Full Disk Access 권한 필요(iMessage `chat.db`). 사용자 동의 후 실행 가정.
- v0.8 의 calibration eval 골든셋(30건 결정 시나리오) 은 사용자 본인이 라벨링 (외부 공개 불가, gitignore).
- 본 로드맵은 단일 개발자(사용자 본인) 운영을 가정. 다중 사용자/멀티 vault 는 범위 외.
