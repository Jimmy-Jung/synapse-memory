# Quickstart — Timeline Recall 단독 데모

본 quickstart 는 *본 feature 단독* 으로 사용자가 받는 가치를 검증한다. 부모 v0.5 의 다른 항목 (feedback, cost, daily resilience, CI) 과 의존성 없음.

## 전제

- `synapse-memory v0.4` 가 동작 중. doctor green.
- vault 에 ProjectCard 3개 + CompanyCard 1개 보유:

```
20_Reference/Projects/
  ├── sample-ios-app.md          period_end: 2025-02-15  status: archived  created: 2024-12-01
  ├── 이력서-2026.md         period_end: 2024-05-01  status: archived  created: 2024-04-20
  └── mobile-ios-slc.md      period_end: null        status: active    created: 2024-08-30
20_Reference/Companies/
  └── 회사A.md               last_reviewed: 2025-03-10
```

- 본 feature 의 브랜치 `002-timeline-recall` 가 체크아웃되어 있고, `endpoints/me.py` / `cli.py` 변경이 머지된 상태.

## 1. 시간순 기본 호출 (FR-001, FR-002, FR-006)

```bash
synapse-memory me what-did-i-think "클린 아키텍처" --timeline
```

기대 출력:

```
## 2025 Q1

- **mobile-ios-slc** (...) — 2026-05-12 (오늘)
  > ...
  [card_project:mobile-ios-slc]

- **회사A** (...) — 2025-03-10 (last reviewed)
  > ...
  [card_company:회사A]

- **sample-ios-app** (Sample iOS App) — 2025-02-15
  > Domain–Data–Presentation 3계층 분리...
  [card_project:sample-ios-app]

## 2024 Q2

- **이력서-2026** (...) — 2024-05-01
  > 도입 기간 2024.01~05, Tuist 멀티 모듈화...
  [card_project:이력서-2026]

총 4개 카드 (--limit 20)
```

검증:
- SC-001 — 4개 카드의 순서가 `mobile-ios-slc > 회사A > sample-ios-app > 이력서-2026` (period_end 기준 desc 순서) Kendall τ = 1.0.
- 분기 헤더 `## 2025 Q1` / `## 2024 Q2` 정확히 일치 (RT-3).
- `mobile-ios-slc` 가 `(오늘 YYYY-MM-DD)` 라벨로 표시 (FR-003).
- `회사A` 가 `(last reviewed)` 라벨 (FR-005).
- `이력서-2026` 은 라벨 없음 (FR-003 기본 케이스).

## 2. 모드 별칭 (FR-009)

```bash
synapse-memory me what-did-i-think "클린 아키텍처" --by time
```

→ §1 과 byte-by-byte 동일 결과.

```bash
synapse-memory me what-did-i-think "클린 아키텍처" --by distance
```

→ 기존 v0.4 의 distance 정렬 결과 (회귀 가드, FR-013).

## 3. 옵션 충돌 (FR-009)

```bash
synapse-memory me what-did-i-think "클린 아키텍처" --timeline --by distance
```

기대:
```
error: --timeline and --by distance conflict — pick one.
```
exit 1.

## 4. `--limit` (FR-010)

```bash
synapse-memory me what-did-i-think "프로젝트" --timeline --limit 2
```

기대: 위 §1 결과에서 상위 2개 카드만 출력. footer `총 2개 카드 (--limit 2)`.

범위 밖:

```bash
synapse-memory me what-did-i-think "프로젝트" --timeline --limit 0
```

→ argparse 에러 + exit 2.

## 5. 결과 0건 (FR-011)

```bash
synapse-memory me what-did-i-think "전혀 매칭 안 되는 주제 zzz" --timeline
```

기대:

```
관련 카드 없음. `synapse-memory daily` 로 vault 수집을 다시 확인하세요.
```
exit 0.

## 6. 모든 메타 null 폴백 (FR-012)

vault 의 모든 매칭 Card 의 period_end / last_reviewed / created 가 비었을 때:

```bash
synapse-memory me what-did-i-think "어떤 주제" --timeline
```

기대:

```
## 시간 정보 없음 — distance 순 폴백

- **<card_id>** (...) — distance 0.31
  > ...
  [card_project:...]
- **<card_id>** (...) — distance 0.42
  > ...
  [card_project:...]
```

exit 0. distance asc 순서.

## 7. 회귀 가드 (FR-013, SC-004)

```bash
synapse-memory me what-did-i-think "클린 아키텍처"
```

→ v0.4 의 출력과 100% 일치. 본 PR 의 회귀 테스트가 byte-by-byte 비교.

---

## 검증 표

| FR | Quickstart 단계 | 검증 방법 |
|---|---|---|
| FR-001 | §1 | `--timeline` 옵션이 동작 |
| FR-002 | §1 | 순서가 period_end desc |
| FR-003 | §1 | active Card 가 `(오늘)` 라벨 |
| FR-004 | (vault fixture 보강 필요) | non-active + period_end null Card 가 `(created)` 라벨 |
| FR-005 | §1 | CompanyCard 가 `(last reviewed)` 라벨 |
| FR-006 | §1 | `## 2025 Q1`, `## 2024 Q2` 헤더 |
| FR-007 | (vault fixture 보강 필요) | 같은 분기 안 ≥ 2 Card 의 `### YYYY-MM` 서브헤더 |
| FR-008 | §4 (`--limit 1`) | 단일 카드 시 헤더 없음 |
| FR-009 | §2, §3 | 별칭 + 충돌 |
| FR-010 | §4 | `--limit` 동작 + 범위 |
| FR-011 | §5 | 0건 메시지 |
| FR-012 | §6 | 메타 null 폴백 |
| FR-013 | §7 | distance 회귀 가드 |
| FR-014 | (별도) | `_interactive_guard` 그대로 |
| FR-015 | (별도) | 디스크 영구 저장 없음 (테스트로 확인) |
| FR-016 | (별도) | prompt 에 raw PII 없음 |
| FR-017 | §1 | 각 라인에 `[card_*:<id>]` 인용 |

---

## 다음 단계

`tests/test_endpoints_me_timeline.py` 의 15개 케이스가 §1~7 시나리오를 자동 검증한다. 사용자가 직접 실행하는 본 quickstart 는 *수동 smoke test* 용도.
