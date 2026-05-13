# Backlog

이 문서는 알려진 한계와 다음 작업 후보를 정리합니다. 우선순위는 실제 사용 중 불편함이 큰 순서로 조정합니다.

## 우선순위 기준

| 등급 | 의미 |
| --- | --- |
| P0 | 사용 중 자주 부딪히는 문제. 다음 패치 후보 |
| P1 | 일주일 이상 사용하며 검증할 개선 |
| P2 | 큰 기능, 의존성 추가, 별도 마일스톤 후보 |

## P0: 바로 다루고 싶은 문제

### Claude Code 메타 문구가 답변에 섞임

증상:

`me decide`, `what-did-i-think` 답변 앞에 `Insight`류의 메타 설명이 가끔 붙습니다.

해결 후보:

- endpoint 후처리에서 메타 블록 제거
- system prompt에 “메타 코멘트 금지” 조건 강화
- Claude Code CLI 옵션 변화 확인

영향 파일:

```text
src/synapse_memory/endpoints/me.py
src/synapse_memory/endpoints/ask.py
tests/test_endpoints_me.py
```

### 한국 회사명 redaction 정확도 부족

증상:

`샘플회사`, `당근마켓` 같은 한국 회사명을 org_name으로 놓치거나 잘못 잡을 수 있습니다.

현재 회피:

```bash
synapse-memory redactlist add "회사명"
```

해결 후보:

- 사용자가 승인한 회사 Card에서 watchlist 생성
- `90_System/AI/Companies-Watchlist.md` 같은 명시 목록 지원
- Pass 2 prompt에 사용자 정의 회사명 주입

### 자동 실행 가이드 보강

현재 [Getting Started](getting-started.md)에 cron 예시만 있습니다.

추가할 내용:

- launchd plist 예시
- 실패 로그 저장 위치
- 월별 비용 cap 전략
- `daily --dry-run`으로 사전 확인하는 흐름

### GitHub Actions 테스트

현재 필요한 기본 CI:

```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv pip install -e '.[dev]'
      - run: pytest -v
```

목표:

- apfel과 Claude Code가 없어도 mock 기반 테스트는 통과
- PR에서 기본 회귀 방지

## P1: 다음 마일스톤 후보

### raw 노트 RAG 인덱싱

현재:

Card만 검색합니다. Card에 반영되지 않은 vault 노트나 Claude Code raw 내용은 직접 검색되지 않습니다.

제안:

- `rag/indexer.py`에 raw note chunk indexing 추가
- chunk metadata에 source, path, chunk index 저장
- Card 결과를 우선하고 raw chunk는 보조 근거로 사용

예상 효과:

- 회상 정확도 증가
- Card를 만들기 전에도 최근 노트 검색 가능

주의:

- raw가 외부 LLM으로 넘어가지 않도록 redaction 경계를 다시 확인해야 함
- 검색 결과가 noisy해질 수 있어 ranking 전략 필요

### BM25 + dense hybrid 검색

현재:

dense vector 검색만 사용합니다.

제안:

- `rank-bm25` 기반 keyword 검색 추가
- dense 결과와 BM25 결과를 RRF로 합치기
- `ask`, `me`에 `--hybrid` 옵션 추가 검토

효과가 큰 query:

- 회사명
- 사람 이름
- 고유명사
- 짧은 한국어 키워드

### Card incremental update

현재:

Card가 이미 있으면 기본 skip이고, `--force`를 쓰면 덮어씁니다.

제안:

```bash
synapse-memory card update dansim-ios
```

원칙:

- 사용자가 쓴 본문은 보존
- 새 raw에서 발견한 근거와 메트릭만 추가 제안
- 변경 전 diff를 보여주거나 draft로 저장

### daily 실행 결과 리포트

제안 출력:

```text
90_System/AI/DailyReports/YYYY-MM-DD.md
```

포함할 내용:

- 수집된 파일 수
- 새 Card 수
- Profile 후보 수
- 실패 단계
- 추정 비용

### 실제 데이터 골든셋

현재:

합성 PII 골든셋 위주입니다.

제안:

- 실제 사용자 raw에서 후보 30개 추출
- 사용자 로컬에서만 라벨링
- `tests/golden/pii_real.json`은 gitignore 처리

## P2: 큰 기능 후보

### 추가 collector

후보:

- iMessage
- KakaoTalk export
- Slack
- Gmail
- Dooray
- 음성 메모

공통 조건:

- incremental mirror
- L0 저장
- redaction 경계 유지
- 외부 API credential 비노출
- 실패해도 다른 daily 단계와 격리

### 답장 초안 endpoint

예상 명령:

```bash
synapse-memory me draft-reply "내일 회의 가능하세요?"
```

사용 재료:

- Profile voice
- 과거 답변 예시
- 관련 프로젝트나 회사 Card

출력:

```text
30_Creative/Drafts/Reply - YYYY-MM-DD.md
```

### 비용 추적

예상 명령:

```bash
synapse-memory cost summary --days 30
```

저장 후보:

```text
~/.synapse/private/cost.jsonl
```

수집할 값:

- command
- model
- total_cost_usd
- input/output token count
- elapsed time

### Profile 자동 promotion

예상 명령:

```bash
synapse-memory me update-profile --auto-promote --min-confidence 0.9
```

위험:

잘못된 fact가 Profile에 들어가면 `me decide` 품질이 낮아집니다. 충분한 검증 전에는 수동 review 흐름을 유지합니다.

### 클론 정확도 향상

후보:

- ProfileFact끼리 모순 검사
- DecisionPattern confidence 추적
- 사용자가 결정 후 결과를 기록하는 feedback loop
- 오래된 패턴의 decay

## 문서와 UX

필요한 개선:

- launchd 자동 실행 가이드
- `ask`, `daily`, `me draft-resume` 실행 화면 예시
- 영어 README
- 5분 demo 영상
- GitHub Release 노트

## CI와 릴리스

후보:

- pytest GitHub Action
- ruff / mypy check
- pre-commit hook
- tag push 시 release note 생성
- changelog 자동화

## v0.2 후보 묶음

v0.2는 아래 네 가지 중 실제 사용 가치가 가장 큰 방향을 우선합니다.

| 후보 | 가치 | 리스크 |
| --- | --- | --- |
| raw note RAG | 검색 품질 크게 향상 | redaction 경계와 noise 관리 |
| Card incremental update | Card가 살아있는 문서가 됨 | 사용자 편집 보존 난이도 |
| 추가 collector | 개인 맥락 확장 | 권한, API, 보안 부담 |
| 클론 정확도 향상 | `me decide` 품질 향상 | 잘못된 Profile 축적 위험 |

## 이슈 보고

GitHub Issues에 올리면 좋은 내용:

- 재현 가능한 버그
- 특정 명령의 실제 출력
- OS, Python, apfel, Claude Code 버전
- 개인정보를 제거한 예시 입력
- 기대한 결과와 실제 결과

PR은 핵심 설계 원칙을 지켜야 합니다. 특히 raw 데이터가 외부 LLM으로 직접 나가지 않는지 반드시 확인합니다.
