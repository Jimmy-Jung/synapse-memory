# Synapse Memory — AI 비서 / 세컨드 브레인 적합성 평가 리포트

> **작성일**: 2026-05-12  
> **버전 기준**: v0.4.0 (459 tests · ~5,500 LOC)  
> **평가자**: JunyoungJung (`/synapse-memory` repo 자체 분석)  
> **범위**: README · architecture · backlog 등 공식 문서가 "약속한 것" vs `src/`·`tests/`에 실제로 구현된 것의 gap 진단

---

## 1. Executive Summary

Synapse Memory v0.4.0 는 **AI 비서·세컨드 브레인 프로토타입으로서 견고한 기반(L0 격리, 2-pass redaction, RAG, daily 파이프라인, 슬래시 endpoint)을 갖추었으나, "기억하고 회상하며 함께 결정하는 동반자" 역할을 완성하기에는 4가지 구조적 결함이 남아 있다.**

| 차원 | 점수 | 한줄 평가 |
|---|---|---|
| **데이터 안전성 (L0 / Redaction)** | A− | 0700·0600 강제, 2-pass redact, redact-list 모두 구현. Pass 3(사용자 검토) 만 미구현 |
| **AI 비서 (`ask`)** | B | RAG + Claude 답변은 동작. 단, 멀티턴/세션 컨텍스트가 없고 답변 인용 품질이 Card 풍부도에 종속 |
| **세컨드 브레인 (`what-did-i-think`)** | C+ | 회상은 동작하나 **시간축 정렬 없음** (cosine distance 정렬만) — "세컨드 브레인"의 핵심 가치 미흡 |
| **클론 / 의사결정 (`decide`)** | C | Profile.md / DecisionPatterns.md 외부 파일에 강하게 의존. Feedback loop·confidence decay 없음 |
| **자동화 (`daily`, plugin)** | B+ | 6단계 idempotent 파이프라인 + Claude Code/Codex slash 6개. 실패 격리·관측은 약함 |
| **테스트 / 코드 품질** | B+ | 459 tests, mypy strict, dataclass·typed errors. 통합/회귀·비용·관측 테스트는 부족 |
| **운영 / UX** | C | doctor 정도만 존재. cost tracking·daily report·launchd 자동 실행 가이드 부재 |

**총평**: **MVP를 졸업했고, β(베타) 진입 직전**. 다음 1~2개 마일스톤을 P0 항목에 집중하면 "내가 매일 쓰는 도구"로 자리잡을 수 있다.

---

## 2. 현재 프로젝트가 가진 기능 (구현 인벤토리)

### 2.1 CLI 서브커맨드 (24개, `src/synapse_memory/cli.py`)

| 분류 | 명령 | 상태 |
|---|---|---|
| 진단 | `doctor` | ✅ 구현 (apfel·macOS·L0 0700 검사) |
| 수집 | `collect claude-code`, `collect obsidian` | ✅ incremental mirror |
| 정제 | `redact backfill claude-code`, `redactlist {show,add,remove}` | ✅ Pass 1+2 일괄 / NDA 리스트 관리 |
| 클러스터링 | `cluster scan`, `cluster classify` | ✅ cwd·폴더 segment 기반 식별 + LLM 분류 |
| 카드 | `card {list,show,new,generate}` | ✅ Project/Company Card CRUD + 자동 초안 |
| 검색 | `rag {index,search}` | ✅ ChromaDB upsert / cosine 검색 |
| 사용자 endpoint | `ask`, `me what-did-i-think`, `me decide`, `me draft-resume`, `me update-profile` | ✅ 모두 구현 (stub 없음) |
| 통합 | `daily`, `daily --dry-run`, `daily --profile-facts-only` | ✅ 6단계 incremental 파이프라인 |
| 평가 | `eval golden` | ✅ 합성 PII 골든셋 F1 측정 |

### 2.2 4-tier 메모리 모델 (`docs/architecture.md` 대비 구현 일치)

| 계층 | 위치 | 외부 LLM 노출 | 구현 |
|---|---|---|---|
| L0 raw | `~/.synapse/private/raw/` (0700) | ❌ | `storage/l0.py` — chmod 강제 |
| L1 redacted | `~/.synapse/private/redacted/` | ⭕ (redacted only) | `redaction/{pass1,pass2}.py` |
| L2 truth | Obsidian vault `20_Reference/Projects/`, `20_Reference/Companies/`, `90_System/AI/Profile.md`, `DecisionPatterns.md` | 사용자 승인 후 검색 재료 | `cards/`, `profile/` |
| L3 index | `~/.synapse/private/rag/chroma/` | ❌ | `rag/{embeddings,indexer,vector_store}.py` |

### 2.3 Plugin layer

- `commands/synapse-{ask,daily,decide,doctor,recall,resume}.md` — Claude Code / Codex 슬래시 명령 6종
- `skills/synapse-memory/` — Skill 매니페스트 + setup/install/e2e/review 보조 명령
- 모든 슬래시 markdown은 `SYNAPSE_FROM_AGENT=1` 을 자동 주입 → 인터랙티브 가드 즉시 통과

### 2.4 LLM 사용 정책

| 도구 | 입력 | 용도 |
|---|---|---|
| **apfel** (로컬, macOS 26 FoundationModels) | raw 허용 | redaction Pass 2, 짧은 분류, profile 추출 |
| **Claude Code CLI** (subprocess, OAuth) | **redacted 만** | Card 생성, `ask`, `me *`, 이력서 |

→ 외부 LLM에 raw가 직접 나가는 코드 경로는 grep으로 확인되지 않음 (정책 준수 ✅).

---

## 3. 잘 구현된 점 (Strengths)

### S1. 보안 boundary 가 코드 레벨에서 강제됨
- `storage/l0.py:ensure_secure_dir()` — `os.chmod(0o700)` 명시, 매 호출마다 검사
- `cmd_doctor` (cli.py)에서 `stat.S_IMODE` 으로 실제 권한 확인 후 표시
- Claude wrapper 가 항상 `--permission-mode bypassPermissions` 로 호출 → tool 호출/파일 접근 차단
- redact-list 가 Pass 1 의 high-priority 항목으로 들어가 사용자 정의 NDA 키워드를 **확정적으로 마스킹**

### S2. Pass 1 + Pass 2 redaction 의 합리적 결합
- Pass 1: regex + Luhn(카드)·KR RRN 체크섬 + JWT/AWS/Bearer 등 **결정적** 패턴 (F1 ≈ 1.00 on synthetic)
- Pass 2: apfel 로컬 LLM 이 자유형 PII (이름·기관·주소·secret) 처리, F1 ≈ 0.83
- **stable index**: 같은 값은 같은 placeholder → 사용자가 사후에 의미를 복원 가능

### S3. Daily 파이프라인의 idempotence 가 실제로 구현됨
- collect: 이미 mirror 된 로그는 offset 이후만 읽음
- classify: `classifications.json` 에 기존 결과 보존, `--resume` 으로 skip
- generate: 기존 Card 파일은 기본 skip, `--force` 만 덮어쓰기
- index: upsert (insert-or-update)
- → "매일 다시 돌려도 부작용 없음" 헌법 원칙 V 와 일치

### S4. 타입 안전성과 에러 분리
- mypy `strict = true` (pyproject.toml)
- dataclass 광범위 사용 — `ProjectCard`, `CompanyCard`, `ProfileFact`, `DecisionPattern`, `Detection`, `SourceCitation`
- 도메인별 예외 클래스: `ClaudeError`, `ApfelError`, `EmbeddingUnavailableError`, `VectorStoreError`

### S5. 테스트 분포가 도메인을 골고루 덮음
- 26개 test 파일, 459 케이스
- redaction (pass1 / pass2 / redact-list), cards (project / company / auto_classify / auto_generate), endpoints (ask / me / me_extra), rag (embeddings / indexer / vector_store), profile, daily, interactive_guard 모두 보유

### S6. 사용자 정책의 명확한 분리
- 대화형 endpoint(`ask`, `me *`) vs 배치 endpoint(`daily`, `doctor`, `collect`, ...) 분리
- 대화형 직접 호출 시 3초 안내 + `SYNAPSE_FROM_AGENT` 우회 — 헌법 원칙 IV 가 실제 코드(`cli.py:_interactive_guard()`)에 1:1 매핑

---

## 4. 부족한 점 / 위험 영역 (Weaknesses)

### W1. 🔴 시간축 회상이 없다 — "세컨드 브레인" 핵심 가치 미달
**증상**: `me what-did-i-think <주제>` 가 cosine distance 순으로만 결과를 반환. Card 가 가진 `created` / `last_reviewed` / `period_start` / `period_end` / `extracted_at` 메타데이터가 정렬에 **전혀 반영되지 않음**.

**왜 문제인가**: 사용자가 "내가 1년 전 클린 아키텍처에 대해 어떻게 생각했었지?" 라고 묻는데, 결과는 "가장 유사한 Card 5개" 일 뿐 시간 흐름이 사라짐. 세컨드 브레인의 정체성과 정면 충돌.

**근거**:
- `src/synapse_memory/endpoints/me.py:what_did_i_think()` — distance 만 사용
- backlog.md 에 시간축 회상이 별도 항목으로 잡혀있지 않음 (사각지대)

### W2. 🔴 Feedback 루프가 없다
**증상**: 답변·결정·이력서가 틀렸을 때 사용자가 "이건 제외", "이 패턴 약화" 같은 신호를 시스템에 줄 수 없다.

**파급**:
- `me decide` 가 잘못된 DecisionPattern 으로 의사결정 → 잘못된 답 → 그대로 누적 → 클론 품질 영구 하락
- ProfileFact 의 `confidence` 가 추출 시점 값으로 고정 (decay 없음)

**근거**:
- ProfileFact / DecisionPattern dataclass 에 `last_validated_at`, `negative_feedback_count` 같은 필드 부재
- endpoint 어디에도 사용자 피드백 수집 기록 코드 없음

### W3. 🟠 RAG 가 Card 단위 인덱싱 — 큰 Card·raw 노트 검색 불가
**증상**: ProjectCard 1개 = vector 1개. 5,000자짜리 Card 의 특정 문단으로 retrieve 불가. Card 에 아직 반영되지 않은 raw 노트는 **검색 자체가 안 됨**.

**근거**:
- `rag/indexer.py` — Card body 전체를 단일 텍스트로 합쳐 embed
- backlog.md P1 에 "raw 노트 RAG 인덱싱"·"BM25 + dense hybrid" 가 이미 잡혀있음 (저자 인지함)

### W4. 🟠 비용 / 토큰 / 시간 관측이 없다
**증상**:
- Claude Code CLI 호출 후 input/output tokens·USD cost 를 **저장하지 않음**
- daily 파이프라인 stage 별 wall-clock 은 stdout 으로만 흘려보냄 (영구 기록 없음)

**파급**: 한 달 뒤 "지난 30일 동안 얼마 썼지?" / "어느 단계가 느려졌지?" 같은 운영 질문을 답할 수 없음. 헌법 원칙 V "Reproducible Daily Pipeline & Observability" 의 절반(reproducible)만 충족.

### W5. 🟠 Pass 3 (사용자 검토 redaction) 미구현
**증상**: architecture.md 는 "Pass 1 결정적 + Pass 2 로컬 LLM" 만 언급. 그런데 실제 위험은 **둘 다 놓친 PII** 가 외부로 나가는 경우. 사용자가 외부 전송 직전 redacted 결과를 1초 훑어볼 UI/CLI 가 없음.

**근거**:
- `me draft-resume` 등은 redacted 텍스트를 곧장 Claude 로 보냄. preview 단계 부재.

### W6. 🟠 Profile.md / DecisionPatterns.md 외부 파일 의존
**증상**: `me decide` 가 동작하려면 vault 의 `90_System/AI/Profile.md`, `DecisionPatterns.md` 가 사용자 손으로 승격되어 있어야 함. 없으면 "없음 — `me update-profile` 필요" 메시지만 출력.

**파급**: 신규 사용자에게 가치 도달까지 시간이 너무 김 (cold-start 문제). MemoryInbox → Profile 승격 과정이 100% 수동.

### W7. 🟡 자동 생성 Card 가 skeleton 수준
**증상**: `cards/auto_generate.py` 가 만든 Card 는 cluster 메타 + 후보 이름·기간·domain 정도. 실제 내용(metrics, role, body)은 사용자가 직접 채워야 함.

**파급**: 자동화 기대치를 깎음. 459 tests 중 auto_generate 가 실제로 "쓸 만한 초안" 을 만드는지 검증하는 케이스 없음 (스키마 정합성만 검증).

### W8. 🟡 멀티턴 대화 / 세션 컨텍스트 없음
**증상**: `ask`·`decide` 는 single-turn. "방금 답변에서 두 번째 항목 더 자세히" 같은 follow-up 이 불가능. 슬래시 명령으로 Claude Code 안에서 호출하면 호스트 LLM이 컨텍스트를 유지하지만, CLI 직접 호출 모드에서는 매번 cold-start.

### W9. 🟡 daily 실패 시 부분 재실행 메커니즘 약함
**증상**: `_run_step()` 이 예외 catch 후 `result.errors += 1` 만 증가시키고 다음 stage 로 진행. 단계 간 데이터 의존성(예: classify 가 실패했는데 generate 진행)이 있을 때 silent corruption 가능.

### W10. 🟡 한국 회사명 redaction 정확도
**증상**: `메가스터디`, `당근마켓` 등 한국 회사명을 Pass 2 가 자주 놓침. 사용자가 `redactlist add` 로 보충해야 함.

**현재 회피**: backlog.md 에서 인지. P0 항목.

### W11. 🟡 CI / lint / mypy 자동화 없음
**증상**: `.github/workflows/` 부재. ruff·mypy 설정은 있으나 PR 게이트가 없음. 헌법 원칙 III(Test-First) 의 "main 은 항상 green" 강제 수단이 사람의 규율에만 의존.

---

## 5. 개선점 (Improvements) — 기존 기능을 더 잘 작동시키기

### I1. `what-did-i-think` 에 시간축 정렬·집계 추가 [영향 ★★★★★]
- retrieve 결과를 distance 가 아닌 `period_start desc` / `created desc` 로 재정렬하는 옵션 (`--by time`)
- "월별 핵심 1줄 요약" 모드: `me what-did-i-think 클린 아키텍처 --timeline`
- 영향 파일: `src/synapse_memory/endpoints/me.py`, `tests/test_endpoints_me.py`

### I2. Feedback CLI 추가 [영향 ★★★★★]
```bash
synapse-memory feedback last --reject "관련 없음"
synapse-memory feedback pattern <pattern_id> --weight -0.3
```
- 저장: `~/.synapse/private/feedback.jsonl`
- ProfileFact·DecisionPattern 에 `last_validated_at`, `confidence_history` 추가
- 재인덱싱 시 confidence < 0.4 항목은 검색 가중치 절반

### I3. raw 노트 chunk RAG (backlog P1 승격) [영향 ★★★★]
- `rag/indexer.py` 에 `index_raw_chunks(path, chunk_size=512, overlap=64)` 추가
- ChromaDB metadata: `source_kind=raw_obsidian | raw_claude_code`, `chunk_index`, `path`
- `ask` 에서 Card 결과를 1차, raw chunk 결과를 2차 근거로 표기

### I4. BM25 + dense hybrid 검색 [영향 ★★★]
- `rank-bm25` 추가, RRF (Reciprocal Rank Fusion) 로 결합
- 회사명·사람 이름·짧은 한국어 키워드에서 효과 큼

### I5. 비용·토큰·시간 관측 레이어 [영향 ★★★★]
- `~/.synapse/private/cost.jsonl` 자동 append (command, model, input/output tokens, USD, elapsed, ts)
- `synapse-memory cost summary --days 30`
- daily 끝에 `DailyReport` 작성 — `90_System/AI/DailyReports/YYYY-MM-DD.md`

### I6. daily 실패 격리 + 재실행 [영향 ★★★]
- `_run_step()` 에 `required_for: list[str]` 추가
- 한 stage 실패 시 의존 stage 는 SKIP 으로 마크 (silent corruption 방지)
- `daily --resume-from index` 옵션

### I7. Pass 3: 외부 전송 직전 preview 모드 [영향 ★★★]
- `ask --preview-prompt`, `me decide --preview-prompt` — Claude 에 보낼 최종 텍스트를 stdout 으로 먼저 출력하고 confirm
- 자동 모드(`SYNAPSE_FROM_AGENT=1`)에서는 비활성

### I8. Profile 자동 승격 (저신뢰) [영향 ★★]
- `me update-profile --auto-promote --min-confidence 0.9` (이미 backlog 에 존재)
- 단, 승격 fact 는 항상 `auto_promoted: true` 메타로 별도 표시 → 신뢰 추적

### I9. CI 추가 [영향 ★★★]
- `.github/workflows/ci.yml` — pytest + ruff + mypy + apfel/Claude mock
- `pre-commit` hook (`ruff --fix`, `mypy --strict`)

### I10. launchd 자동 실행 가이드 [영향 ★★]
- `docs/operations.md` 신설 — `~/Library/LaunchAgents/com.synapse.daily.plist` 템플릿, 실패 로그 위치, 월별 비용 cap 전략

---

## 6. 추가해야 할 기능 (New Features) — 로드맵

### Phase A — v0.5: "쓰면 더 똑똑해지는 도구" (4~6주)
| # | 기능 | 슬래시 / CLI | Why |
|---|---|---|---|
| A1 | **Timeline 회상** (I1) | `/synapse-recall --timeline` | 세컨드 브레인 핵심 |
| A2 | **Feedback 루프** (I2) | `/synapse-feedback`, CLI 동일 | 클론 품질의 유일한 학습 신호 |
| A3 | **비용 / 토큰 관측** (I5) | `synapse-memory cost summary` | 30일 후 자기 도구 신뢰 |
| A4 | **DailyReport** (I5) | `daily` 종료 시 자동 | "어제 뭐 했지" 자동 답변 |
| A5 | **daily 실패 격리** (I6) | `daily --resume-from <stage>` | 운영 안정성 |
| A6 | **CI 추가** (I9) | GitHub Actions | 헌법 원칙 III 강제 |

### Phase B — v0.6: "맥락 폭 확장" (6~8주)
| # | 기능 | Why |
|---|---|---|
| B1 | **raw 노트 chunk RAG** (I3) | Card 미반영 노트도 검색 |
| B2 | **BM25 hybrid** (I4) | 고유명사·짧은 키워드 정확도 |
| B3 | **Pass 3 preview** (I7) | 외부 전송 최종 안전망 |
| B4 | **답장 초안 endpoint** | `me draft-reply <text>` — Profile voice + 관련 Card |
| B5 | **Card incremental update** | `card update <id>` — 사용자 본문 보존 + 새 근거만 제안 |

### Phase C — v0.7: "맥락 입력 채널 확장" (별도 마일스톤)
| # | 기능 | Why |
|---|---|---|
| C1 | **iMessage / KakaoTalk export collector** | "내가 그 사람에게 뭐라고 했지" 회상 |
| C2 | **Gmail / Slack / Dooray collector** | 업무 맥락 통합 |
| C3 | **음성 메모 collector** (Whisper 로컬) | 이동 중 생각 캡처 |
| C4 | **Browser history 발췌 collector** | 학습 / 리서치 흐름 |

### Phase D — v0.8+: "클론 정확도" 마일스톤
| # | 기능 | Why |
|---|---|---|
| D1 | **ProfileFact 모순 검사** | 충돌 패턴 자동 경고 |
| D2 | **DecisionPattern confidence decay** | 1년 된 패턴 자동 감쇠 |
| D3 | **결정 후 결과 기록** (`me decide --outcome <good|bad>`) | RLHF-lite |
| D4 | **Multi-turn ask 세션** | `~/.synapse/private/sessions/<id>.jsonl` 으로 컨텍스트 유지 |
| D5 | **Calibration eval** | "decide 가 추천한 N건 중 사용자가 따른 비율" 추적 |

### Phase E — 인터페이스 확장 (병행 가능)
- **macOS menubar app** (gptel 스타일) — daily 결과 알림, 1-clik `ask`
- **iOS Shortcuts** — 위젯에서 `/synapse-ask` 호출 (Local-first 원칙 위반 없도록 USB/Tailscale 경유)
- **Obsidian plugin** — 노트에서 우클릭 → "관련 카드 보기" / "이 노트로 Card 생성"

---

## 7. 헌법 원칙 적합성 체크

| 원칙 (constitution.md v1.0.0) | 현재 준수도 | 갭 |
|---|---|---|
| I. Local-First & Privacy by Default | ✅ 95% | iCloud chmod OSError 무시 케이스 만 미관측 |
| II. Two-Pass Redaction (NON-NEGOTIABLE) | ✅ 90% | Pass 3 preview 부재 (W5) |
| III. Test-First Discipline (NON-NEGOTIABLE) | 🟠 75% | CI 미존재 (W11), feedback / cost / timeline 회로 미테스트 |
| IV. Conversation-Context-Aware Endpoints | ✅ 95% | `_interactive_guard` 정상 + `SYNAPSE_FROM_AGENT` 가드 모두 동작 |
| V. Reproducible Daily Pipeline & Observability | 🟠 65% | idempotence ✅ / 관측은 stdout 일회성 ❌ (W4, W9) |

---

## 8. 액션 아이템 우선순위 (다음 1개월)

### 🔴 P0 — 이번 주 안
1. **CI 워크플로 추가** (I9) — 0.5일. 헌법 원칙 III 강제
2. **`docs/operations.md` + launchd 가이드** (I10) — 0.5일. 사용자 첫 30일 안정화
3. **Claude 메타 문구 후처리** (backlog P0) — 0.5일. UX 첫인상 개선

### 🟠 P1 — 이번 달 안
4. **Timeline 회상** (I1) — 1주. 세컨드 브레인 정체성 회복
5. **Feedback CLI + jsonl 저장** (I2) — 1주. 학습 신호 확보
6. **비용 / 토큰 / 시간 관측 레이어** (I5) — 1주. 운영 신뢰
7. **daily 실패 격리** (I6) — 3일. 운영 안정성

### 🟡 P2 — 다음 분기
8. raw 노트 chunk RAG (I3)
9. BM25 hybrid (I4)
10. Pass 3 preview (I7)
11. 답장 초안 endpoint (B4)

---

## 9. 부록 — 점검 시 사용한 시그널

- 코드 인용: `src/synapse_memory/cli.py:_interactive_guard()`, `daily.py:_run_step()`, `storage/l0.py:ensure_secure_dir()`, `redaction/pass1.py:_assign_stable_indices()`, `endpoints/me.py:what_did_i_think()`, `rag/indexer.py:index_cards()`, `profile/extract.py:142,206`
- 테스트 분포: `tests/test_redaction_pass1.py` 11KB, `test_redaction_pass2.py` 29KB (가장 큼), `test_endpoints_me.py`, `test_daily.py` 1.4KB (가장 작음 — 통합 부족 신호)
- 문서 인용: `docs/architecture.md` §"4단계 메모리 모델", `docs/backlog.md` §P0, §P1, §P2, `README.md` "3가지 핵심 목표" 표
- 헌법: `.specify/memory/constitution.md` v1.0.0

---

**결론** — Synapse Memory 는 *"raw 데이터를 안전하게 가둬두는"* 1단계와 *"검색·답변·이력서를 만든다"* 2단계를 모두 끝낸 드문 개인용 도구다. 다음 1개월은 **회상의 시간축 복원 + 사용자 피드백 수집 + 운영 관측** 세 축에 자원을 몰면, 진짜 "내가 매일 켜는 두 번째 뇌" 단계로 진입할 수 있다. 그 뒤에야 collector 확장(C1~C4)·클론 정확도(D1~D5)의 투자 회수가 시작된다.
