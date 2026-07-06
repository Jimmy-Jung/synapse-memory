# Feature Specification: Timeline Recall (시간축 회상)

**Feature Branch**: `002-timeline-recall`
**Created**: 2026-05-12
**Status**: Draft
**Input**: User description: "timeline 회상에 period_end 기반 시간순 정렬 추가 (FR-A1)"

부모 plan: `specs/001-roadmap/plan.md` (FR-A1), 평가 리포트 `docs/assessment-2026-05-12.md` §W1, research `specs/001-roadmap/research.md` §R1.

## User Scenarios & Testing *(mandatory)*

도구 소유자(사용자 본인)가 *과거의 자기 자신*을 시간 흐름으로 다시 만나는 시나리오. 현재 `me what-did-i-think` 은 cosine 유사도 순으로만 결과를 반환해 "1년 전 → 6개월 전 → 최근" 같은 회상의 본질적 시간 감각을 잃는다. 본 feature 는 시간축을 1순위 정렬 키로 끌어올린다.

### User Story 1 — 주제별 월/분기 시간순 회상 (Priority: P1)

사용자가 특정 주제(예: "클린 아키텍처", "이직 고민") 를 입력하면 관련된 ProjectCard / CompanyCard 가 가장 최근의 `period_end` 부터 가장 오래된 순서로 정렬되어, 월·분기·연도 그룹 헤더와 함께 표시된다.

**Why this priority**: 평가 리포트가 지적한 "세컨드 브레인 정체성 결손" 의 핵심. 시간축이 없으면 회상이 아니라 그냥 검색이다. 단독으로도 즉시 사용자 가치.

**Independent Test**: vault 에 `period_end` 가 2024-03·2024-05·2024-09·2025-02 인 ProjectCard 4개가 존재하는 상태에서 `synapse-memory me what-did-i-think "<공통 주제>" --timeline` 호출 시, 4개가 2025-02 → 2024-09 → 2024-05 → 2024-03 순으로 출력되고, 분기 그룹(`2025 Q1`, `2024 Q3`, `2024 Q2`, `2024 Q1`)이 헤더로 나타난다.

**Acceptance Scenarios**:

1. **Given** vault 에 6개월 이상에 걸친 ProjectCard ≥ 3개와 관련 RAG 결과가 존재, **When** `me what-did-i-think <topic> --timeline` 실행, **Then** 결과가 `period_end desc` 1차·`created desc` 2차 정렬되어 표시된다.
2. **Given** 같은 분기 안에 Card 가 2개 이상 존재, **When** timeline 출력, **Then** 동일 분기 헤더 하위에 두 Card 가 모두 표시되고 둘 사이는 `period_end desc` 로 정렬된다.
3. **Given** Card 의 `period_end` 가 null 인 `status=active` Card 가 결과에 포함, **When** timeline 출력, **Then** 해당 Card 는 "오늘(`YYYY-MM-DD`)" 라벨과 함께 가장 최근 그룹에 배치된다.
4. **Given** CompanyCard 는 `period_*` 필드가 없음, **When** timeline 출력, **Then** `last_reviewed` 가 정렬 키로 사용되고 라벨에 "(last reviewed)" 가 표시된다.
5. **Given** 사용자가 `--timeline` 없이 호출, **When** 기존과 동일하게 distance 순 출력, **Then** 본 변경이 기존 동작에 회귀를 주지 않는다.

---

### User Story 2 — 결과 0건 / 시간 메타 부재 시의 명확한 폴백 (Priority: P2)

`--timeline` 호출 결과가 0건이거나, 매칭된 Card 의 모든 시간 메타가 null 일 때 사용자가 무슨 상황인지 즉시 이해할 수 있어야 한다.

**Why this priority**: 잘못된 침묵(silent 0건)은 사용자에게 "도구가 망가졌나" 라는 신호를 주므로 회상 신뢰를 깎는다. P1 만큼 시급하지는 않지만, 첫 출시에 빠지면 안 됨.

**Independent Test**: vault 가 비어있는 상태 또는 모든 Card 의 `period_end` 와 `last_reviewed` 가 null 인 상태에서 `--timeline` 호출 시 명시적 안내 메시지가 출력되고 종료 코드는 0 이다.

**Acceptance Scenarios**:

1. **Given** vault 에 어떤 Card 도 없음, **When** `me what-did-i-think <topic> --timeline`, **Then** "관련 카드 없음. `synapse-memory daily` 로 vault 수집을 다시 확인하세요." 메시지 + exit 0.
2. **Given** RAG retrieve 결과는 있으나 모든 항목의 시간 메타가 null, **When** `--timeline`, **Then** "시간 정보 없음 — distance 순 폴백" 헤더 + 기존 distance 정렬 결과.

---

### User Story 3 — 정렬 모드 명시 옵션 (Priority: P3)

사용자가 회상 모드와 검색 모드를 명시적으로 전환할 수 있다.

**Why this priority**: `--timeline` 만으로도 충분하지만, 향후 `--by time-asc` 같은 확장을 안전하게 받기 위한 옵션 표면.

**Independent Test**: `--by time` / `--by distance` 두 변형이 동일 쿼리에 대해 서로 다른 정렬 결과를 반환해야 한다.

**Acceptance Scenarios**:

1. **Given** 동일 쿼리, **When** `--by time` 호출, **Then** `--timeline` 과 동일한 결과를 반환한다 (시맨틱 일치).
2. **Given** 동일 쿼리, **When** `--by distance` 호출, **Then** 기존 cosine 정렬 결과를 반환한다.
3. **Given** `--timeline` 과 `--by distance` 가 동시에 주어짐, **When** 명령 실행, **Then** "충돌 옵션" 오류 + exit 1.

---

### Edge Cases

- **Card 1개만 결과**: 그룹 헤더 없이 단일 라인으로 표시 (헤더 노이즈 제거).
- **`period_end` 가 미래**: 사용자가 향후 종료 예정으로 적은 경우 그대로 미래 라벨로 표시 (검열 없음).
- **`period_end` 와 `created` 모두 null + status≠active**: distance 폴백 그룹 하단에 따로 표시.
- **Card 가 1년 이내 5개 같은 달**: 같은 월 안에서는 `created desc` 보조 정렬 → 최신 작성이 위.
- **NFC 정규화 차이로 같은 topic 다중 매칭**: 본 feature 범위 외 (RAG 단의 책임). 동일 카드 중복 제거 만 보장.
- **결과가 ≥ 50건**: timeline 헤더 폭증 방지 — 기본 limit 20 으로 잘라내고 `--limit N` 으로 조정 가능.
- **부분 메타**: `period_end` 만 있고 `period_start` 없음 → 라벨에 `~ <period_end>` 만 표시.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST `me what-did-i-think <topic> --timeline` CLI 옵션을 제공한다.
- **FR-002**: `--timeline` 활성 시 결과는 1차 `period_end desc`, 2차 `created desc` 로 정렬되어야 한다 (R1).
- **FR-003**: ProjectCard 의 `period_end` 가 null 이고 `status=active` 인 경우 시스템은 정렬 시 *오늘 날짜* 로 폴백하고, 출력 라벨에 "오늘 (`YYYY-MM-DD`)" 를 표시해야 한다.
- **FR-004**: ProjectCard 의 `period_end` 가 null 이고 `status≠active` 인 경우 시스템은 정렬 시 `created` 로 폴백하고, 출력 라벨에 "(created)" 를 표시해야 한다.
- **FR-005**: CompanyCard 는 `period_*` 필드가 없으므로 정렬 시 `last_reviewed` 를 사용하고, 출력 라벨에 "(last reviewed)" 를 표시해야 한다.
- **FR-006**: System MUST 결과를 *분기 단위 그룹* (예: `2024 Q3`, `2024 Q4`) 으로 묶고, 같은 그룹 내에서는 정렬 순서를 보존하여 출력한다.
- **FR-007**: System MUST 같은 월 안에 ≥ 2개 Card 가 있을 때 월 헤더(예: `2024-09`) 를 분기 헤더의 하위 헤더로 출력한다.
- **FR-008**: System MUST 매칭된 Card 가 1개 이하인 경우 그룹 헤더 없이 단일 라인으로 출력한다.
- **FR-009**: System MUST `--by time` (alias for `--timeline`) 와 `--by distance` 두 모드를 제공한다. `--timeline` 과 `--by distance` 가 동시 지정되면 종료 코드 1 로 충돌 오류를 반환한다.
- **FR-010**: System MUST `--limit N` (기본 20) 으로 출력 결과 수를 제한한다.
- **FR-011**: System MUST 매칭 결과 0건일 때 "관련 카드 없음. `synapse-memory daily` 로 vault 수집을 다시 확인하세요." 안내를 출력하고 종료 코드 0 으로 종료한다.
- **FR-012**: System MUST 매칭된 모든 Card 의 시간 메타가 null 인 경우, "시간 정보 없음 — distance 순 폴백" 헤더와 함께 기존 distance 정렬 결과를 출력한다.
- **FR-013**: System MUST `--timeline` 미지정 시 본 변경 이전과 동일한 distance 정렬 결과를 반환해야 한다 (회귀 가드).
- **FR-014**: System MUST 본 명령을 헌법 §"Conversation-Context-Aware Endpoints" 의 *대화형* 으로 분류하고, TTY 직접 호출 시 3초 안내 + `SYNAPSE_FROM_AGENT=1` 즉시 통과를 적용한다.
- **FR-015**: System MUST 정렬·그룹화 결과를 vault·L0 어디에도 영구 저장하지 않는다 (stateless query).
- **FR-016**: System MUST 본 명령이 외부 LLM 으로 보내는 텍스트는 기존 `redact_full()` 경로를 그대로 사용하며, 신규 raw 우회 경로를 만들지 않는다 (헌법 원칙 II).
- **FR-017**: System MUST timeline 출력 라인별로 source Card 의 `card_id` 와 `display_name` 을 인용으로 표기한다 (기존 SourceCitation 포맷과 호환).

### Key Entities

본 feature 는 신규 entity 를 만들지 않는다. 기존 ProjectCard·CompanyCard·SourceCitation 의 *읽기 전용* 사용에 한정한다.

다만 출력 표현 단위로 *임시* 그룹화 객체를 도입:

- **TimelineGroup** (transient, in-memory only): `{quarter_label: str, year: int, quarter: int, sort_ts: datetime, members: list[CardWithMeta]}`
- **CardWithMeta** (transient, in-memory only): `{card_id: str, display_name: str, source_kind: Literal["card_project","card_company"], sort_ts: datetime, sort_ts_source: Literal["period_end","created","last_reviewed","today_fallback"], distance: float | None, citation_text: str}`

두 객체 모두 명령 호출 끝에 GC. 디스크에 영구 저장되지 않는다 (FR-015).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 합성 골든 셋(`tests/golden/timeline_recall/<set>.json`, 30 쿼리 × 평균 5개 결과) 에서 `--timeline` 결과의 시간 순서가 정답 시간 순서와 **Kendall τ ≥ 0.9** (지표는 결과 행 단위, 동률은 보조 정렬 키로 결정).
- **SC-002**: vault Card 500개 가정 시 `--timeline` 정렬·그룹화의 정렬 단계(post-retrieve)가 **로컬 머신에서 200 ms 이하**.
- **SC-003**: 단일 사용자가 v0.5 출시 30일 후 누적 회상 명령(`what-did-i-think`) 의 **70% 이상이 `--timeline` 또는 `--by time`** 으로 호출 (사용 패턴 검증, opt-in 메트릭).
- **SC-004**: 회귀 가드 — `--timeline` 미지정 호출이 이전 버전과 **결과 카드 순서·인용 텍스트가 100% 일치** (기존 459 tests + 신규 회귀 테스트로 검증).
- **SC-005**: 빈 결과 / 시간 메타 부재 / 옵션 충돌 3가지 분기 모두에서 종료 코드와 사용자 메시지가 spec 와 1:1 일치 (3개 unit test 통과).
- **SC-006**: 사용자가 1주일간 timeline 회상 결과에 대해 `feedback last --reject` 를 사용한 비율이 distance 모드보다 **낮거나 같다** (회상 적합성 신호; v0.5 의 feedback 루프 도입 이후 측정 가능).

## Assumptions

- ProjectCard 의 `period_start` / `period_end` 가 `YYYY-MM-DD` 또는 `YYYY-MM` 포맷으로 입력되었다고 가정. `YYYY-MM` 인 경우 해당 월 말일로 정규화하여 비교.
- CompanyCard 는 `period_*` 필드 부재가 정상이며, `last_reviewed` 가 항상 채워져 있다고 가정 (`card new` 명령이 채움).
- "분기" 는 양력 기준(`Q1 = 1~3월`, `Q2 = 4~6월`, ...) 으로 한국 회계분기(`Q1 = 4~6월`) 등은 사용하지 않는다.
- 매칭은 기존 `endpoints/me.py:what_did_i_think()` 의 RAG retrieve 결과 풀에서 *재정렬* 만 수행한다. retrieve 자체(임베딩 기반 top-K) 는 변경하지 않는다.
- ChromaDB 가 retrieve 결과로 함께 반환하는 metadata 에 `period_end`, `created`, `last_reviewed`, `status` 가 이미 색인되어 있다고 가정 (`rag/indexer.py` 가 이미 색인 중). 누락 필드는 별도 PR 로 색인 보강.
- 본 feature 는 P1 단독 출시 가능. v0.5 의 다른 항목(feedback, cost, daily resilience, CI) 과는 의존성 없음.
- 본 spec 은 `me what-did-i-think` 에 한정한다. `ask` 와 `me decide` 의 timeline 옵션은 별도 spec (`002-x-*` 또는 `006-*` 이후) 으로 다룬다.
