# 019 — LLM-maintained Wiki 재설계 (Synapse Memory v2)

- 상태: Draft (설계 합의 완료, 구현 계획 대기)
- 작성일: 2026-06-14
- 기반 문서: [Karpathy — LLM Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- 선행 스펙: [017-knowledge-compounding](../017-knowledge-compounding/proposal.md), [001-roadmap](../001-roadmap/spec.md)
- 전제: 1인 사용 · 개발 단계 · **마이그레이션 불필요**(그린필드 재작성 허용)

---

## 1. 목표 (What we want)

LLM이 Claude / GPT / Codex / Cursor 등 **어떤 툴에서 돌아가든** 나와 LLM의 상호작용을
항상 인식하고, 나의 wiki(세컨드브레인)를 **자동으로 구축·유지**하는 시스템.

현재 시스템의 한계:

1. `synapse-memory daily`를 **사람이 매일 수동 실행**해야 함.
2. 신규 cluster → 새 카드 **생성만** 하고 기존 페이지를 **갱신하지 않음** (지식이 누적되지 않음).
3. 카드 간 **링크가 없음** (세컨드브레인의 핵심인 그래프 부재).
4. ask 답변이 `last_response` JSON으로 **증발** — 질문할수록 똑똑해지지 않음.
5. 모순·낡음·고아를 잡는 **lint 부재**.
6. 로컬 LLM(apfel) 기반 redaction이 복잡도를 키우고 품질을 떨어뜨림 (불필요로 판단됨).

---

## 2. 핵심 결정 (Locked decisions)

| # | 결정 | 선택 | 근거 |
|---|---|---|---|
| D1 | wiki 유지 LLM 엔진 | **기존 `claude`/`codex` CLI headless 재사용** | 별도 API 키 불필요, `llm/{claude,codex,ai_api}.py` 어댑터 재활용, 비용은 기존 구독에 흡수, 평소 쓰는 모델과 품질·말투·한국어 일관 |
| D2 | 엔진 선택 시점 | **설치/셋업 시 명시 선택 → `config`에 고정** | 자동 폴백을 기본으로 두지 않음(일관성). `config set maintenance_engine`으로 재설정. `doctor`가 가용성 검증 |
| D3 | 자동 트리거 | **유휴(idle) 감지 실시간 파일 감시** (launchd + 워처) | 모든 툴이 파일/SQLite로 흔적을 남김 → 파일 워처 하나로 균일 캡처. 유휴 N분 = "대화 종료" 근사치, 부분 로그 ingest 방지 |
| D4 | redaction | **완전 제거** (apfel + 2-pass + redacted 계층 삭제) | 클라우드 툴 신뢰 전제. 파이프라인 대폭 단순화, 품질 향상 |

---

## 3. 아키텍처 — Karpathy 3계층 매핑

```
┌─ L0  RAW (불변, 진실원본) ──────────────────────────────┐
│  collectors/* → ~/.synapse/raw/<tool>/                   │  ★ 유지 (이미 강력)
│  claude_code · codex · cursor · aider · continue ·       │  ✗ redacted/ 계층 삭제
│  obsidian · git · shell · ...  (14종)                    │
└──────────────────────────────────────────────────────────┘
                   │  (유휴 감지 → ingest)
                   ▼
┌─ L1  WIKI (LLM이 소유·유지하는 마크다운) ───────────────┐
│  Obsidian vault                                          │  ★ vault 유지 (그래프 무료)
│   ├─ Entities/  Projects, Companies, People              │  ⟳ 카드 → "통합형 페이지"로
│   ├─ Concepts/  기술·의사결정·주제                        │     재작성 (integrate-not-index)
│   ├─ Profile/   당신에 대한 사실·패턴                     │
│   ├─ Insights/  ask 답변 write-back                       │
│   ├─ index.md   전체 카탈로그/overview                    │  + [[위키링크]] 그래프
│   └─ log.md     시간순 변경 기록                          │
└──────────────────────────────────────────────────────────┘
                   ▲  (wiki-first 검색 + 답변 환원)
                   │
┌─ L2  SCHEMA.md (이 시스템의 "CLAUDE.md") ───────────────┐  + 신규
│  페이지 분류·작성 규칙·링크 규약 +                        │  툴-무관의 핵심:
│  ingest / query / lint 작업 지침을 한 파일에 정의          │  어떤 에이전트든 이걸 읽으면
│  → claude/codex CLI가 이걸 읽고 wiki를 유지               │  wiki 유지법을 알게 됨
└──────────────────────────────────────────────────────────┘
```

### 컴포넌트 처분표

| 처분 | 대상 | 이유 |
|---|---|---|
| ★ **유지** | `collectors/*`, `llm/{claude,codex,ai_api}.py`, `rag/*`(재조준), Obsidian vault + `moc`, `hooks/session_start`, `config`, `doctor`, `cost/*` | 캡처·엔진·그래프·관측은 이미 자산 |
| ⟳ **재작성** | `daily.py` → 백그라운드 **유지 워커**(ingest/integrate/lint 잡), `cards/*` → 통합형 wiki 페이지 모델(갱신+링크), `endpoints/ask.py` → wiki-first + write-back | 단방향→양방향, 수동→자동 |
| ✗ **삭제** | `llm/apfel.py`, `redaction/*`(pass1, pass2, patterns, redactlist), redacted L0 계층, local-classify | D4 반영 |
| + **신규** | `SCHEMA.md`, `synapse-memory watch` 데몬 + launchd plist, ingest/integrate/lint 잡 모듈, 링크그래프 유지, `index.md`/`log.md` 생성기 | 자동·통합·연결 |

---

## 4. 자동 유지 루프 (수동 `daily` 폐기)

```
launchd (로그인 시 자동 기동, KeepAlive)
  └─ synapse-memory watch  ← 상주 데몬
       │
       │ ① 파일 워처: ~/.claude, ~/.codex, Cursor SQLite, ~/.zsh_history ...
       │    (FSEvents/watchdog — 변경 이벤트 수신)
       ▼
   ┌─ 디바운스 큐 ─────────────────────────────┐
   │ 변경 감지 → 타이머 리셋.                     │
   │ "유휴 N분(기본 3분)" 도달 = 대화 종료 신호    │  ← 부분 로그 ingest 방지
   │ → 해당 소스를 ingest 잡으로 enqueue          │
   └──────────────────────────────────────────┘
       │
       ▼  (단일 동시성 워커 + 파일 락)
   ┌─ INGEST 잡 ───────────────────────────────────────────────┐
   │ 1. collector가 raw 미러 갱신 (증분)                          │
   │ 2. 새 raw 조각 + 관련 기존 wiki 페이지 + SCHEMA.md 를         │
   │    프롬프트로 묶어 claude/codex CLI headless 호출            │
   │ 3. 에이전트가 "통합 diff" 반환:                              │
   │      - 기존 페이지 갱신 (10~15개)  ← integrate-not-index     │
   │      - 신규 entity/concept 페이지 생성                       │
   │      - [[위키링크]] 추가/보정                                 │
   │ 4. diff를 vault에 원자적 적용 + log.md에 1줄 기록             │
   └────────────────────────────────────────────────────────────┘
       │
       ▼  (주기적: 하루 1회 idle 타이머)
   ┌─ LINT 잡 ─────────────────────────────────────────────────┐
   │ wiki 전체 스캔 → 모순/낡음/고아/끊긴 링크 탐지 →             │
   │ 자동 수정 가능한 건 패치, 판단 필요한 건 index.md에 큐잉      │
   └────────────────────────────────────────────────────────────┘
       │
       ▼  (wiki 변경 시)
   rag 인덱스 재빌드 (wiki 페이지 대상) + index.md/MOC 갱신
```

### 설계 포인트

| 항목 | 설계 |
|---|---|
| **동시성** | ingest는 항상 1개씩 (파일 락). CLI 호출 직렬화 → vault 충돌·비용 폭주 방지 |
| **유휴 임계값** | `config`에 `idle_minutes`(기본 3). 툴별 오버라이드 가능 |
| **엔진 선택** | `config.maintenance_engine`(D2). 기본 폴백 off |
| **실패 격리** | 잡 단위 try/catch. 한 소스 실패해도 데몬 생존. 실패 잡은 재시도 큐 (`daily.py --resume-from`의 노하우 계승) |
| **수동 탈출구** | `synapse-memory ingest --now` / `lint --now` 즉시 강제 실행 (디버깅·초기 백필) |
| **관측성** | `synapse-memory status`가 큐 깊이·마지막 ingest·비용 보고. `cost/*` 유지 |

> 참고: 기존 `daily.py`의 stage는 사라지지 않고 **잡(job)으로 변신**한다. integrate-not-index의 실제 구현은 INGEST 3단계의 **프롬프트 설계**(관련 기존 페이지 동봉)가 핵심이며, 그 컨텍스트 선별에 rag(wiki 검색)가 1차로 쓰인다.

---

## 5. wiki 페이지 모델

```
vault/
├─ Entities/
│   ├─ Projects/<slug>.md     # 프로젝트 진실원본 (이력서·면접 자산)
│   ├─ Companies/<slug>.md    # 회사·지원내역·JD
│   └─ People/<slug>.md       # 인물 (신규)
├─ Concepts/<slug>.md         # 기술·의사결정원칙·반복 주제 (신규)
├─ Profile/<slug>.md          # 당신의 사실·선호·결정패턴
├─ Insights/<yyyy>/<mm>/<slug>.md   # ask 답변 write-back
├─ index.md                   # 전체 카탈로그 + lint 큐 + overview
└─ log.md                     # 시간순 변경 로그 (grep 친화)
```

### 공통 frontmatter

```yaml
---
type: project|company|person|concept|profile|insight
slug: <id>
related: ["[[other-slug]]", ...]   # 양방향 링크 그래프
sources: [raw 조각 참조]            # provenance (어느 대화에서 왔는지)
updated: 2026-06-14
status: active|stale|review         # lint가 관리
---
```

설계 원칙:
- **양방향 링크**: A→B 링크 시 lint가 B→A 역링크 보장 → Obsidian Graph 자동 활성.
- **provenance(`sources`)**: "이 주장 어디서 나왔지?" 추적 + lint가 낡은 주장을 raw와 대조해 갱신.

---

## 6. 검색 + 답변 환원 (`/sm:ask`, `$ask`)

```
질문
  │
  ▼
① rag 검색 (대상 = wiki 페이지, raw 아님)  ← BM25+vector, 이미 보유
  │   (raw는 wiki에 답이 없을 때만 --include-raw 폴백)
  ▼
② 선별된 wiki 페이지 + SCHEMA.md → claude/codex CLI 합성
  │   각 주장에 [[페이지]] 인용
  ▼
③ 답변 반환 + (가치 있으면) Insights/ 에 write-back
  │   → 새 Insight 페이지도 wiki의 일부가 되어 다음 질문에 재사용
  ▼
   "질문할수록 똑똑해지는" 누적 루프 완성
```

핵심: **rag를 raw에서 wiki로 재조준**. raw는 잡음이 많지만 wiki 페이지는 LLM이 이미
정제·교차참조한 고밀도 지식 → 검색 정확도·답변 품질 동시 상승. raw 검색은 안전망.

---

## 7. 범위 밖 (Out of scope, YAGNI)

- 마이그레이션 도구 (1인 개발, 기존 데이터 폐기 허용).
- 로컬 LLM / on-device 추론 (D4).
- 멀티유저·동시쓰기 동기화.
- 자동 폴백을 기본 동작으로 강제 (D2: 명시 선택 우선).

---

## 8. 세부 결정 (Resolved)

| # | 항목 | 결정 |
|---|---|---|
| R1 | 파일 워처 | **macOS 네이티브 FSEvents** (launchd `WatchPaths`). 크로스플랫폼 불필요 → `watchdog` 미채택, 더 가벼움 |
| R2 | INGEST 컨텍스트 선별 | **하이브리드**: ① 엔티티 이름 매칭(정확) + ② 의미 유사도 top-k(rag) + ③ 링크 1-hop 확장(인접 맥락). 토큰 예산으로 상한 |
| R3 | lint 경계 | **"구조는 자동, 진실은 사람"**. 자동수정: 역링크 보강·고아 연결·frontmatter 정규화·죽은 링크 정리. 검토 큐(`index.md`): 모순·낡음 의심·병합 후보 |
| R4 | `SCHEMA.md` 위치 | **vault 루트** (Obsidian에서 직접 편집 가능) |
| R5 | 초기 채움 | **빈 vault 재구축** (기존 카드 폐기). 첫 가동 시 raw 전체를 **재개 가능한 청크 ingest**로 1회 구축. 변환기 미작성 |

### R2 상세 — INGEST 컨텍스트 선별

새 대화 조각으로 기존 페이지를 갱신하려면 "관련 기존 페이지"를 프롬프트에 동봉해야 한다
(wiki 전체는 토큰·비용·컨텍스트 한계로 불가). 세 전략을 합쳐 후보를 회수하고 토큰 예산으로 상한:

- **엔티티 이름 매칭**: 조각에서 프로젝트/회사/사람 이름 추출 → 기존 페이지 slug 직접 대조 (싸고 정확).
- **의미 유사도 top-k**: 조각 임베딩 → rag로 유사 페이지 k개 (이름이 안 맞아도 주제로 포착).
- **링크 1-hop 확장**: 위 후보가 `[[링크]]`로 가리키는 이웃 페이지도 회수 (그래프 인접 맥락).

### R3 상세 — lint 자동수정 vs 검토 큐

LLM이 환각으로 기록을 오염시키는 것을 막기 위한 방어선. 정답이 데이터 안에 있으면 자동,
데이터 밖(진위 판단)이면 사람.

- **자동수정 (구조적·가역적)**: 끊긴 역링크 보강(A→B면 B→A), 고아 페이지를 index에 연결,
  frontmatter/포맷 정규화, 존재하지 않는 페이지를 가리키는 죽은 `[[링크]]` 정리.
- **사람 검토 큐 (`index.md`)**: 사실 모순(예: 입사연도 충돌), 낡음 의심, 병합 후보(같은 엔티티 중복 페이지).

### R5 상세 — 빈 vault 재구축

"마이그레이션 불필요 + 개발 단계" 전제에 부합. 기존 ProjectCard/CompanyCard는 폐기하고,
첫 가동 시 raw 전체 이력을 새 스키마로 처음부터 구축한다. 초기 백필은 **재개 가능한 청크 ingest**
(시간/프로젝트 단위 배치, 단일 동시성)로 비용·중단 위험을 통제 — `daily --resume-from` 노하우 계승.
