# Backlog — 남은 작업

v0.1.0 이후 점진 패치 + 확장 계획.
실제 사용 중 발견되는 약점 우선순위로 진행.

## 우선순위 분류

- **🔴 즉시** — 사용 중 자주 마주치는 문제. 다음 패치(v0.1.x)에 포함.
- **🟡 단기** — 일주일 사용 후 결정. v0.2 마일스톤.
- **🟢 장기** — 큰 기능, 의존성 추가. v0.3+ 또는 별도 PR.

---

## 1. 알려진 약점 (패치 후보)

### 🔴 Claude Code `★ Insight` 박스 새어듦

**증상**: `me decide`, `what-did-i-think` 응답 앞에 가끔
````
`★ Insight ─────────────────────────────────────`
이 Skill은 ... 관련 없습니다. ... 직접 분석합니다.
`─────────────────────────────────────────────────`
````
가 등장. Claude Code의 explanatory output style이 `--system-prompt` 명시에도 일부 새어듦.

**해결**:
- system prompt 강화: "응답 첫 문자는 ``-`` 또는 답변 내용이어야. Insight 박스, 메타 코멘트 절대 금지."
- 후처리: `endpoints/me.py`, `endpoints/ask.py`에서 ``\`★ Insight`` 블록 자동 strip
- claude CLI `--exclude-dynamic-system-prompt-sections` 시도 (`--system-prompt`와 호환되는지 검증)

### 🔴 org_name 한국 회사 검출 F1=0.50

**증상**: 메가스터디, 당근마켓 같은 한국 회사를 Pass 2(apfel)가 못 잡거나 false positive.

**현재 보완**: 사용자가 `redactlist add 회사명`으로 직접 차단.

**향후**:
- vault `90_System/AI/Companies-Watchlist.md` 같은 진실원본 list 자동 학습
- Pass 2 system prompt에 사용자 vault에서 추출된 회사명 inject

### 🟡 address span 모호

**증상**: 골든셋에서 "부산광역시 해운대구 해운대로 456" vs "...로 456 빌딩" 둘 다 정답 가능.

**해결**:
- evaluator에 fuzzy match 추가 (Levenshtein 또는 substring overlap >= 0.8)
- 또는 system prompt에 "끝 단어(빌딩/타워 등) 제외" 강화

### 🟡 짧은 영어 이름 누락 (Mike)

**증상**: "Mike" 같은 4자 이하 영어 이름이 path/identifier 휴리스틱과 충돌.

**현재**: `_looks_like_path_or_identifier`가 6자+ 소문자 영어 단어를 reject. "Mike"는 5자라 통과는 함. 하지만 모델이 잘 안 잡음.

**해결**:
- 자주 등장하는 영어 이름 dictionary 보강 (선택)
- 또는 ask에서 사용자가 직접 "Mike는 사람 이름이야"라고 명시할 수 있는 hint 기능

### 🟡 "User Assistant System" multi-word false positive

**증상**: chat role label 3개를 합쳐서 person_name으로 잡는 모델 실수.

**해결**: NON_PII_TERMS 매칭을 단어 단위 → 공백 분할 후 모든 단어가 NON_PII_TERMS면 reject.

### 🟡 한국 도시명 false positive ("서울" → person_name)

**해결**: `_KOREAN_CITIES = {"서울", "부산", "대구", ...}` deny-list. person/org 카테고리에서 reject.

### 🟢 sensitive_topic 카테고리 정의 모호

**증상**: "RRN" 같은 단어를 sensitive_topic으로 잡는 케이스 (실제 RRN 값이 아니라 단어 자체).

**해결**: sensitive_topic 정의 강화. "구체적 사적 사실"로 명시. 또는 카테고리 제거.

---

## 2. 기능 확장

### 🟡 raw 노트 RAG 인덱싱

**현재**: Card만 11 vectors. Card 외 raw 노트는 검색 안 됨.

**해결**:
- `rag/indexer.py`에 `index_raw_notes(source="obsidian"|"claude_code")` 추가
- vault 1330 .md → 청크 분할 (paragraph, max_tokens=600) → bge-m3 → ChromaDB
- 메타: `source_kind="raw_obsidian"`, `path`, `chunk_idx`
- 검색 시 Card 우선 + raw 보충 (rerank 또는 weighted)

**비용**: 1330 청크 × 1024 dim float = ~10MB ChromaDB. 임베딩 시간 ~10분 (M-series + MPS).

### 🟡 BM25 + hybrid 검색

**현재**: dense (cosine) 만. 한국어 고유명사 (회사명, 사람 이름)에서 정확도 90% 정도.

**해결**:
- `rag/bm25.py` — rank-bm25 + 한국어 tokenizer (단순 whitespace 또는 KoNLPy)
- `rag/retrieval.py` — RRF (Reciprocal Rank Fusion): dense + BM25 → 통합 ranking
- `ask` / `me`에 옵션 `--hybrid` 추가, 기본 dense

### 🟢 추가 collector

우선순위 (사용자 환경 기준):
- **iMessage** — 로컬 SQLite (FullDiskAccess 필요). 한국 사용자라 카톡보다 신호 적음
- **카카오톡** — 데스크톱 export 수동 백업 + 자동 파싱
- **Slack** — User token + conversations.history API
- **Gmail** — OAuth + Gmail API
- **Dooray (메일+메시지)** — 회사 보안 정책 확인 필요
- **음성** — Granola 사용 안 함. Voice memo는 backlog

각 수집기는:
- `collectors/<source>/mirror.py`
- 변경분 detection (incremental)
- L0 격리, redact 통과 후 RAG 인덱싱

### 🟡 `me draft-reply <메시지>`

받은 메시지 → 사용자 톤으로 답장 초안.

```bash
synapse-memory me draft-reply "내일 회의 가능하세요?"
# → vault Drafts/Reply - YYYY-MM-DD.md
```

설계:
- 메시지 → embed → 비슷한 과거 대화 retrieve (있으면)
- + Profile.md voice 학습 결과
- → Claude → 답장 초안

### 🟢 Card 갱신 (incremental merge)

**현재**: Card 한 번 생성하면 `--force`로만 재생성 (덮어쓰기).

**해결**: 기존 Card body는 유지 + frontmatter 메트릭만 새 raw 정보로 추가. 사용자 편집 보존.

```bash
synapse-memory card update dansim-ios   # 기존 body 유지 + 새 정보 add
```

### 🟢 비용 추적 endpoint

```bash
synapse-memory cost summary --days 30
```

`~/.synapse/private/cost.jsonl` 누적 로그. Claude 호출 시 envelope `total_cost_usd` 추출.

### 🟢 `me update-profile` 자동 promotion

사용자 검토 부담 → 일정 confidence 이상은 자동으로 `Profile.md`에 머지.

```bash
synapse-memory me update-profile --auto-promote --min-confidence 0.9
```

**위험**: 잘못된 fact가 Profile에 들어가면 클론 모드가 망가짐. 일주일 사용 후 결정.

---

## 3. 골든셋 / 평가

### 🟡 실제 데이터 골든셋 30개

**현재**: 합성 58개. 실제 사용자 raw 30개 누락.

**해결**:
- `synapse-memory eval extract-candidates --limit 30` 명령 추가
- 사용자가 ProfileFact / DecisionPattern PR 검토 시점에 동시 라벨링
- `tests/golden/pii_real.json` 별도 (gitignore — 사용자별 다름)

### 🟢 apfel 옵션 검증 골든셋

apfel 새 버전 출시 시 옵션 호환성 자동 체크.

```bash
synapse-memory eval apfel-options
# → 모든 wrapper 옵션 (--system, -o json, --temperature 등) 호출 시도
```

---

## 4. 자동화 / 운영

### 🔴 crontab / launchd 셋업 가이드

`docs/getting-started.md`에 일부 있지만 더 구체적으로:
- launchd plist 예시
- 실패 시 vault에 에러 로그
- 비용 캡 (월 $50 등)

### 🟡 daily 실행 결과 알림

vault에 `90_System/AI/DailyReports/YYYY-MM-DD.md` 자동 생성:
- 추가된 Card
- update-profile 후보 수
- 비용

### 🟡 단계별 실패 격리

현재 `daily`의 한 단계 실패 시 다음 단계 계속 진행. OK이지만:
- 실패 패턴 누적 → 같은 실패 N번이면 알림
- 일부 실패는 retry (네트워크 에러 등)

### 🟢 라이브 watcher

vault 변경 → 즉시 incremental collect + index. fswatch / watchdog 기반.

---

## 5. 보안 강화

### 🟡 Pass 1 패턴 추가

- 한국 운전면허번호 (XX-XX-XXXXXX-XX)
- 한국 여권번호 (M12345678, S12345678 등)
- 한국 사업자등록번호 (XXX-XX-XXXXX)
- 계좌번호 (은행별 다름)

### 🟢 PII 골든셋 다양화

현재 합성 위주. 실제 사용자 데이터의 분포에 맞게 보강.

### 🟢 회사 자동 학습 → redact-list

vault `90_System/AI/`에 NDA 회사 list 사용자가 표시 → 자동으로 redact-list에 합류.

---

## 6. UX / 문서

### 🔴 GitHub Release v0.1.0 노트 작성

태그는 만들었지만 Release 페이지 본문 미작성. GitHub UI에서 추가.

### 🟡 사용 예시 GIF / 스크린샷

README에 `ask` / `me draft-resume` / `daily` 실행 화면.

### 🟡 영어 README (`README.en.md`)

영어권 사용자 접근성. macOS 사용자에 영어권 많음.

### 🟢 시연 영상 (5분)

YouTube / Twitter. 첫 사용자 onboarding.

### 🟢 GitHub Discussion 채널

사용자 질문 + 발견된 약점 보고.

---

## 7. CI / 개발 인프라

### 🔴 GitHub Actions — pytest 자동

`.github/workflows/test.yml`:

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

apfel/Claude Code 미설치 환경에서도 459 tests 중 거의 모두 mock 위주라 통과해야.

### 🟡 ruff / mypy lint check CI

코드 품질 자동.

### 🟢 pre-commit hooks

`pre-commit-config.yaml` — 커밋 전 자동 ruff format + pytest.

### 🟢 Release 자동화

`v0.1.x` 태그 push 시 GitHub Release 자동 생성 + changelog.

---

## 8. 큰 그림 — v0.2 마일스톤

W6 패치 (v0.1.x) 마무리 후 v0.2 후보:

### A. raw 노트 RAG 확장 (가장 valuable)
- Card 외 raw 노트도 검색 가능
- vault 1330 노트 + Claude Code 113MB 인덱싱
- 검색 결과 풍부, 회상 정확도 ↑

### B. Card 갱신 흐름 (incremental merge)
- 사용자 편집 보존 + 새 정보 추가
- Card가 진짜 살아있는 문서 됨

### C. 추가 collector — 메시지 / 메일
- 현재 Claude Code + Obsidian만
- 진짜 Tier-3 약속 이행

### D. 클론 정확도 향상
- Profile.md / DecisionPatterns.md 자동 검증
- 일관성 체크 (서로 모순되는 fact)
- DecisionQualityRegistry 자동 추적

각 방향 1-2주 소요. 사용 패턴 보고 결정.

---

## 참여 / 이슈 보고

[GitHub Issues](https://github.com/Jimmy-Jung/synapse-memory/issues)에서:
- 발견된 버그
- 새 기능 요청
- 알려진 한계의 회피 경험

PR 환영. 단 핵심 설계 5가지 결정 (Tier-3 / 5분 / apfel / Apple Silicon+Tahoe / redacted-only)에 부합해야.
