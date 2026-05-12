# CLI Contract — `me what-did-i-think` (Timeline Recall)

본 contract 는 `synapse-memory me what-did-i-think` 의 *신규 옵션*·*인자 충돌*·*exit code*·*출력 포맷* 을 정확히 정의한다.

## 명령 시그니처

```
synapse-memory me what-did-i-think <topic> [options]
```

### 옵션

| 옵션 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `<topic>` | str (positional) | required | 회상 주제 (사용자 자유 입력) |
| `--timeline` | flag | false | 시간순 정렬 + 분기 그룹 헤더 활성화 (`--by time` 동의) |
| `--by {time,distance}` | enum | `distance` | 정렬 모드. `time` = `--timeline` 와 동일. |
| `--limit N` | int | `20` | 출력 카드 최대 수. `1 ≤ N ≤ 100`. 범위 밖은 argparse 에러. |
| `--model M` | str | (기존 기본) | 기존 옵션 유지 (Claude 모델 선택) |

### 옵션 충돌 (FR-009)

| 입력 | 결과 |
|---|---|
| `--timeline` AND `--by distance` | argparse 에러 메시지 + exit 1 |
| `--timeline` AND `--by time` | 동일 의미, 충돌 아님 (passthrough) |
| `--timeline` 단독 | OK |
| `--by time` 단독 | OK, `--timeline` 과 동일 |
| `--by distance` 단독 | OK (기존 거동) |
| 옵션 모두 미지정 | OK, `--by distance` 기본 (FR-013 회귀 가드) |

### Exit Code

| 상황 | code |
|---|---|
| 정상 출력 (결과 ≥ 0 건) | 0 |
| 결과 0건 (FR-011 메시지 출력) | 0 |
| 모든 메타 null (FR-012 폴백 메시지 출력) | 0 |
| 옵션 충돌 (FR-009) | 1 |
| `--limit` 범위 밖 | 2 (argparse) |
| 외부 LLM 호출 실패 | 1 |

### Stdout 출력 — `--timeline` ON

#### 정상 케이스 (그룹 ≥ 2, 카드 ≥ 2)

```
## 2025 Q1

- **dansim-ios** (Dansim iOS App) — 2025-02-15
  > <Card body excerpt, redacted, ≤ 200 chars>
  [card_project:dansim-ios]

## 2024 Q4

### 2024-09

- **mobile-ios-slc-tablet** (...) — 2024-09-10 (last reviewed)
  > ...
  [card_company:mobile-ios-slc-tablet]

(... 추가 그룹)

총 N개 카드 (--limit 20)
```

#### 단일 카드 (FR-008)

```
- **이력서-2026** (...) — 2024-05-01
  > ...
  [card_project:이력서-2026]
```

(그룹 헤더 없음)

#### 결과 0건 (FR-011)

```
관련 카드 없음. `synapse-memory daily` 로 vault 수집을 다시 확인하세요.
```

#### 모든 메타 null (FR-012)

```
## 시간 정보 없음 — distance 순 폴백

- **<card_id>** (...) — distance 0.31
  > ...
  [card_project:...]

(... distance asc)
```

### Stdout 출력 — `--timeline` OFF (회귀 가드, FR-013)

기존 v0.4 출력과 byte-by-byte 동일. 본 contract 는 *변경 없음* 을 보장한다. `test_endpoints_me.py` 의 회귀 케이스가 이를 검증한다.

---

## 인터랙티브 가드 (FR-014, 헌법 §IV)

기존 `cli.py:cmd_me_what_did_i_think:350` 의 `_interactive_guard("me what-did-i-think", "recall")` 호출 그대로. 본 변경 없음.

```
TTY 직접 호출 → 3초 안내 → 진행
SYNAPSE_FROM_AGENT=1 → 즉시 통과
stdout 파이프 → 즉시 통과
```

---

## Redaction 게이트 (FR-016, 헌법 §II)

- ChromaDB 가 반환하는 Card body 는 이미 redacted (인덱싱 시점에 Pass1+Pass2 통과).
- `--timeline` 의 분기 헤더(`## 2024 Q3`)·라벨(`(오늘 ...)`)은 본 라이브러리가 *생성* 하는 텍스트로 PII 가 들어갈 가능성 없음.
- Claude 호출 시 prompt 는 기존 `endpoints/me.py:_build_prompt()` 경로 — 변경 없음.

assertion (테스트):
- 출력 stdout 에 redaction placeholder 패턴 (예: `<EMAIL_N>`, `<PHONE_N>`) 가 leak 되지 않는다 (이미 redacted 결과만 흐르므로 자명).
- Claude wrapper 의 prompt argument 에 *raw* PII 패턴 (`<REDACTED_EXAMPLE_EMAIL_LIKE_TOKEN>` 같은 합성 토큰을 fixture 로 주입) 이 포함되지 않는지 검증.

---

## Slash 명령 (`commands/synapse-recall.md`)

신규 옵션 안내 추가:

```markdown
---
description: 주제 회상 — 시간순(timeline) 또는 유사도(distance) 정렬
---
Run `SYNAPSE_FROM_AGENT=1 synapse-memory me what-did-i-think $ARGUMENTS`

옵션:
- `--timeline` 시간순 분기 그룹 (권장 — 회상 본연의 경험)
- `--by distance` 유사도 순
- `--limit N` 출력 카드 수 제한 (기본 20)
```

`SYNAPSE_FROM_AGENT=1` 누락 시 CI 정적 검사가 거부한다 (부모 plan §B5).
