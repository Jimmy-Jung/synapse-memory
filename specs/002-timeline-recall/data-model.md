# Phase 1 — Data Model (Timeline Recall)

본 feature 는 *디스크에 영구 저장되는 신규 entity 가 없다* (FR-015). 출력 표현을 위한 in-memory transient 객체 2개만 도입한다.

## 표기

- `datetime` = UTC ISO-8601
- `Date` = `YYYY-MM-DD`
- 모든 신규 dataclass 는 `frozen=True` 권장

---

## 1. CardWithMeta (transient)

```python
@dataclass(frozen=True)
class CardWithMeta:
    card_id: str                         # 예: "dansim-ios"
    display_name: str                    # 예: "Dansim iOS App"
    source_kind: Literal["card_project", "card_company"]
    sort_ts: datetime                    # 1차 정렬 키
    sort_ts_source: Literal[
        "period_end",
        "today_fallback",
        "created",
        "last_reviewed",
        "no_time_meta",
    ]
    created_ts: datetime                 # 2차 정렬 키 (없으면 datetime.min)
    distance: float | None               # 원래 cosine distance
    citation_text: str                   # 기존 SourceCitation 포맷 그대로
    body_redacted: str                   # 외부 LLM 전달용 redacted 본문 (기존 SourceCitation 의 발췌)
```

### 생성 위치
- `endpoints/me.py:_resolve_sort_ts()` 가 ChromaDB retrieve 결과 1건당 `CardWithMeta` 1개 생성.

### 검증 규칙
- `sort_ts_source == "no_time_meta"` 이면 distance 폴백 그룹에 들어감 (FR-012).
- `body_redacted` 는 ChromaDB 가 반환한 텍스트(이미 redact 통과한 Card body) — 추가 redact 호출 없음 (FR-016).

---

## 2. TimelineGroup (transient)

```python
@dataclass(frozen=True)
class TimelineGroup:
    quarter_label: str                  # "2024 Q3"
    year: int
    quarter: int                        # 1~4
    sort_ts: datetime                   # 그룹 내 최대 sort_ts (그룹 자체 정렬용)
    members: tuple[CardWithMeta, ...]   # 그룹 내 카드들, 이미 정렬됨
    months_present: tuple[int, ...]     # 같은 분기 내 등장 월 (FR-007 의 월 헤더 출력 트리거)
```

### 생성 위치
- `endpoints/me.py:_group_by_quarter()` 가 정렬된 `CardWithMeta` 리스트를 입력으로 받아 그룹 리스트 생성.

### 정렬 규약
- `TimelineGroup` 리스트는 `sort_ts desc` (= 최신 분기 위).
- `members` 는 `CardWithMeta.sort_ts desc, created_ts desc` (FR-002).

---

## 상태 전이

```
ChromaDB retrieve result (raw dict)
        │
        ▼
_resolve_sort_ts ─→ CardWithMeta (1개)
        │
        ▼ (정렬: stable sort by (sort_ts desc, created_ts desc))
list[CardWithMeta]
        │
        ▼ (그룹화: 같은 (year, quarter))
list[TimelineGroup]
        │
        ▼ (포맷: markdown)
str (stdout 출력)
```

각 단계는 stateless. 명령 종료 시 모든 객체 GC. 디스크 영구 저장 없음.

---

## 분류 표 — `sort_ts_source` 결정 트리

```
Card 가 ProjectCard 인가?
├── 예
│   ├── period_end 가 valid date 인가?
│   │   ├── 예  → sort_ts_source = "period_end"
│   │   └── 아니오
│   │       ├── status == "active" → sort_ts_source = "today_fallback", sort_ts = today
│   │       └── status != "active" → sort_ts_source = "created"
│   └── (created 도 없는 경우)
│       └── sort_ts_source = "no_time_meta"
└── 아니오 (CompanyCard 등)
    ├── last_reviewed 가 valid date 인가?
    │   ├── 예  → sort_ts_source = "last_reviewed"
    │   └── 아니오 → sort_ts_source = "no_time_meta"
```

이 분류 결과가 출력 라벨에 그대로 반영된다 (FR-003~005).

---

## 출력 라벨 매핑

| sort_ts_source | 출력 라벨 |
|---|---|
| `period_end` | (라벨 없음 — 기본 케이스) |
| `today_fallback` | `(오늘 YYYY-MM-DD)` |
| `created` | `(created)` |
| `last_reviewed` | `(last reviewed)` |
| `no_time_meta` | 폴백 그룹 헤더 "## 시간 정보 없음 — distance 순 폴백" 아래에 표시 |

---

## 관계도

본 feature 는 신규 영구 entity 가 없으므로 *읽기* 관계만 존재:

```text
ChromaDB chunks/cards collection
   │  (read-only retrieve)
   ▼
ProjectCard.{period_end, period_start, status, created, last_reviewed} (existing metadata)
CompanyCard.{last_reviewed, created}                                    (existing metadata)
   │
   ▼ (transient transform)
CardWithMeta → TimelineGroup → stdout str
```

기존 `cards/project.py`·`cards/company.py` 에 `CardWithMeta` 라는 이름은 *존재하지 않음* — `CardWithMeta` 는 본 feature 가 새로 도입하는 이름. 충돌 시에는 `endpoints/me.py` 내부 모듈-스코프로 한정 (export 안 함).
