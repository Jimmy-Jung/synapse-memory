# Phase 0 — Research (Timeline Recall)

본 research 는 본 feature 가 코드 작성 전에 확정해야 할 5건의 결정을 정리한다. 부모 plan 의 R1(부모 `specs/001-roadmap/research.md`) 을 본 feature 맥락으로 확장하고, 나머지 4건은 단일 feature 범위에서 정한다.

## RT-1. `period_end` 폴백 우선순위

- **Decision**: 정렬 키 결정 우선순위는 다음과 같다.
  1. ProjectCard 의 `period_end` (있음)
  2. ProjectCard 의 `period_end == null` AND `status == "active"` → 오늘 날짜
  3. ProjectCard 의 `period_end == null` AND `status != "active"` → `created`
  4. CompanyCard 는 `period_*` 부재 → `last_reviewed`
  5. 모든 시간 메타 null → distance 폴백 그룹 (FR-012)
- **Rationale**: 부모 R1 의 결정을 그대로 채택하되, `status` 분기를 명시화. active 카드는 "현재진행형 기억" 으로 회상의 최상단에 와야 자연스러움.
- **Alternatives**:
  - `last_reviewed` 단독 폴백: 검토 시점이 사건 시점과 멀어질 수 있어 부정확. 기각.
  - 모든 null → distance 정렬: 사용자가 "왜 시간 정보 없는데 timeline 결과가 있지?" 라고 혼란. 별도 폴백 그룹이 더 정직.

## RT-2. `YYYY-MM` 입력의 *월 말일* 정규화

- **Decision**: `period_end` 가 `YYYY-MM` 포맷이면 `YYYY-MM-31` 로 정규화 (단, 30/29/28일 월은 그 월의 최종일). 즉 `calendar.monthrange(y, m)[1]`. 이렇게 하면 "2024-03 종료" 와 "2024-03-31 종료" 가 동일 정렬값을 갖는다.
- **Rationale**: 사용자는 종종 일 단위 정밀도가 없는 시기에 `YYYY-MM` 만 적음. 월 시작(`YYYY-MM-01`)으로 정규화하면 같은 월 내 일 단위 입력보다 *이른* 시점이 되어 의도와 어긋남.
- **Alternatives**:
  - `YYYY-MM-15` 로 정규화 (중앙): 안전하지만 사용자 의도 추측. 기각.
  - 정규화 거부 → 예외: 회상 명령에서 예외 발생은 UX 손상. 기각.

## RT-3. 분기 라벨 포맷

- **Decision**: `2024 Q3` (영문 Q + 공백 1개). 한국어 본문 안에서도 이 라벨이 가독성 가장 높음. 출력 헤더는 `## 2024 Q3` 형식 (markdown h2).
- **Rationale**: `2024-Q3` 는 dash 가 ISO 일자처럼 보여 혼란. `Q3 2024` 는 영어 순서가 한국어 본문 흐름에서 어색. 골든셋·테스트에 이 정확한 문자열을 assert.
- **Alternatives**: `2024년 3분기` (한국어): 다국어 확장 시 부담. 기각.

## RT-4. `--limit` 기본값

- **Decision**: 기본 `20`. `--limit N` 로 1~100 사이 지정 가능. 100 초과는 argparse 검증으로 거부.
- **Rationale**: 한 번에 보는 회상량의 적정선. 분기 헤더 5~7개 + 카드 평균 3개/분기 = 약 20개. 사용자가 더 길게 보고 싶으면 명시.
- **Alternatives**:
  - 기본 10: 회상 맥락이 너무 좁아짐. 기각.
  - 무제한: 한 번 호출에 50+ 카드 출력 → 노이즈. 기각.

## RT-5. distance 폴백 시 user-facing 메시지

- **Decision**:
  - 결과 0건: `관련 카드 없음. \`synapse-memory daily\` 로 vault 수집을 다시 확인하세요.`
  - 모든 메타 null: `시간 정보 없음 — distance 순 폴백`
- **Rationale**: 사용자가 다음 행동(=`daily` 재실행)을 알 수 있는 actionable 메시지. distance 폴백은 *원인* 을 알려야 침묵 오해를 방지.
- **Alternatives**: 단순 "0 results" — actionable 아님. 기각.

---

## 베스트 프랙티스 — 본 feature 한정

### BT-1. 정렬 안정성 (stable sort)
- Python 의 `sorted()` 는 stable. 1차 키 동률 시 입력 순서를 보존하므로, 2차 키 `created desc` 는 명시적 `key=` 튜플로 표현해야 함:

```python
sorted(items, key=lambda c: (-c.sort_ts.timestamp(), -c.created.timestamp()))
```

### BT-2. Edge — `created` 도 null 인 Card
- `created` 가 `""` 또는 null 이면 `datetime.min` 으로 보정 → 가장 오래된 자리로 자연 정렬. 별도 로직 불필요.

### BT-3. 골든셋 합성 전략
- 30 쿼리. 각 쿼리당 5~10건 결과. period_end 분포를 의도적으로 흩뿌림:
  - 1/3: 1년 이내 (현재)
  - 1/3: 1~3년 (회상의 메인)
  - 1/6: 3년 이상 (과거)
  - 1/6: period_end null (status active/inactive 절반씩)
- 골든은 query · expected_card_id_order 두 컬럼만. Kendall τ 계산은 테스트가 수행.

### BT-4. metadata 누락 graceful 처리
- ChromaDB 결과의 `result["metadatas"][i]` 가 `None` 이거나 키 누락이면 → `_resolve_sort_ts` 가 distance 폴백으로 마킹. 예외 발생 금지.

### BT-5. `_interactive_guard` 변경 금지
- 본 feature 는 `cli.py:350` 의 guard 호출을 *그대로* 유지. argparse 옵션 추가는 guard 호출 이후 단계의 인자 전달만 영향.

---

## 결정 요약표

| ID | 결정 | 출처 |
|---|---|---|
| RT-1 | 폴백 4-단계 (period_end → today → created → last_reviewed → distance) | 부모 R1 확장 + FR-003~005 |
| RT-2 | `YYYY-MM` → 월 말일 정규화 | spec Assumptions §1 보강 |
| RT-3 | `## 2024 Q3` 헤더 포맷 | UX 일관성 |
| RT-4 | `--limit` 기본 20 | 분기 헤더 가독성 + 회상 깊이 |
| RT-5 | actionable 폴백 메시지 2종 | FR-011, FR-012 |
