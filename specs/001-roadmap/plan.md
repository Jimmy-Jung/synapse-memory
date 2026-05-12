# Implementation Plan: Roadmap v0.5 → v0.8 (Synapse Memory Meta-Plan)

**Branch**: `001-roadmap` | **Date**: 2026-05-12 | **Spec**: `specs/001-roadmap/spec.md`
**Input**: Feature specification from `specs/001-roadmap/spec.md`

## Summary

`docs/assessment-2026-05-12.md` 가 진단한 11개 결함(W1~W11)을 4개 마일스톤(v0.5~v0.8) + 1개 병행 인터페이스 트랙(E)으로 묶어 단계적으로 해소한다. 본 plan 은 *meta-plan* 으로서 각 Phase 의 (a) 기술 컨텍스트, (b) 헌법 게이트, (c) 의존성, (d) Phase-별 자체 spec 으로 위임할 항목을 정의한다. 개별 FR 구현 세부(예: BM25 라이브러리 인터페이스, OAuth 토큰 회전 로직)는 본 plan 산출물(`research.md`, `data-model.md`, `contracts/`)이 결정 가이드라인을 제공하고, 각 Phase 의 자체 `specs/00X-<name>/plan.md` 에서 코드 레벨 세부를 결정한다.

**전체 기술 접근**: 기존 모듈 경계(`collectors/`, `redaction/`, `rag/`, `endpoints/`, `cards/`, `profile/`) 를 유지한 채 (1) 두 개의 새 모듈(`feedback/`, `cost/`) 을 추가하고, (2) `daily.py` 에 stage dependency·skip·resume 메커니즘을 주입하고, (3) `rag/` 에 chunk indexer 와 hybrid retriever 를 추가하고, (4) `endpoints/` 에 session-aware 변종을 도입한다. 새 외부 의존: `rank-bm25`, `faster-whisper`, `google-api-python-client`(선택), Whisper 모델 weights(로컬 캐시).

## Technical Context

**Language/Version**: Python 3.11+ (헌법 §Platform floor)
**Primary Dependencies**: 기존 — `chromadb`, `sentence-transformers` (bge-m3), `pydantic`, `pyyaml`, `apfel` (외부 CLI), Claude Code CLI(외부 binary). 신규 — `rank-bm25` (Phase B), `faster-whisper` (Phase C, 로컬 Whisper), `google-api-python-client` + `google-auth-oauthlib` (Phase C-Gmail, 선택), `sqlite3` (Phase C-iMessage, stdlib).
**Storage**:
- L0: `~/.synapse/private/` (0700) — raw, redacted, rag/chroma, **신규**: `feedback.jsonl`, `cost.jsonl`, `sessions/<id>.jsonl`, `.tokens/` (Phase C OAuth)
- L2 vault: `<vault>/90_System/AI/DailyReports/`, `<vault>/30_Creative/Drafts/Reply-*.md` (신규)
**Testing**: 기존 pytest (459 tests baseline). 신규: mock-based CI (apfel/Claude 없이 통과), integration 골든셋(redaction F1, RAG NDCG, calibration follow-rate).
**Target Platform**: macOS 26 Tahoe + Apple Silicon (헌법 §Platform floor — 변경 시 MINOR bump 필요)
**Project Type**: CLI library (entry: `synapse-memory` console script)
**Performance Goals**:
- `daily` 총 wall-clock ≤ 5분 (incremental, ProjectCard < 200개 가정)
- `ask --hybrid` p95 ≤ 4s (retrieve 단계만, Claude 호출 제외)
- `cost summary --days 30` ≤ 1s
- timeline 회상 정렬 ≤ 200ms (vault Card 500개 가정)
**Constraints**:
- Pass1 F1 ≥ 0.95, Pass2 F1 ≥ 0.80 (헌법 §Security & Privacy — eval gate)
- raw 데이터의 외부 LLM 직송 절대 금지 (헌법 원칙 I, II)
- `daily` idempotence 보장 (헌법 원칙 V)
- 헌법 §"Spec Kit flow" — 각 Phase 의 PR 머지 전 Plan-time Constitution Check 통과
**Scale/Scope**:
- vault Cards: 50~500 (현재 v0.4 baseline ~10~50 예상)
- daily raw 증가량: ~수 MB/일 (Claude Code session + Obsidian diff)
- collector 추가 (Phase C): iMessage chat.db ~수 GB (incremental 처리 필수)

## Constitution Check

*GATE: Phase 0 research 진입 전 + Phase 1 design 후 두 차례 재평가.*

| 원칙 | 본 plan 의 준수 방식 | 위반 위험 / 완화책 |
|---|---|---|
| I. Local-First & Privacy by Default | 신규 jsonl(`feedback`, `cost`, `sessions`) 모두 `~/.synapse/private/` 하위에 0700 권한. OAuth 토큰(Phase C)은 `~/.synapse/private/.tokens/` 0600. | Gmail/iMessage collector 가 외부 API 응답 처리 중 raw leak 가능 — 모든 collector 가 Pass1+Pass2 통과 후에만 redacted/* 작성하도록 강제 (FR-X2). |
| II. Two-Pass Redaction (NON-NEGOTIABLE) | 신규 collector 4개, draft-reply, session 컨텍스트 모두 기존 `redact_full()` 거치도록 endpoints 진입 직전 게이트. `--preview-prompt` (FR-B3) 가 Pass 3 (사용자 검토)을 추가한다. | preview 가 비대화형 모드에서는 비활성 → `SYNAPSE_FROM_AGENT=1` 이 우회 경로가 되지 않도록 raw 검증 단위 테스트 추가 (Phase 1 contract). |
| III. Test-First Discipline (NON-NEGOTIABLE) | FR-A8 (CI 추가) 가 P1 안에 포함. FR-X3 가 각 FR 당 최소 1개 테스트를 요구. | 25개 FR × 1 test = ~25 신규 테스트 + 통합 골든셋 — 기존 459 tests + ~50 으로 확장 추정. coverage ≥ 80% 유지. |
| IV. Conversation-Context-Aware Endpoints | 신규 endpoint(`draft-reply`, `feedback`, `cost`, `ask --session`) 분류: `feedback`·`cost`·`card update`·`collect *` = 배치, `draft-reply`·`ask --session` = 대화형. 대화형은 `_interactive_guard()` 통과 후 `SYNAPSE_FROM_AGENT` 우회 적용. | slash 명령 markdown(`commands/*.md`) 새로 추가 시 `SYNAPSE_FROM_AGENT=1` 주입 누락 가능 — Phase 1 contracts 에 slash markdown 템플릿 포함. |
| V. Reproducible Daily Pipeline & Observability | FR-A3 (cost.jsonl), FR-A5 (DailyReport), FR-A6 (stage required_for + SKIP), FR-A7 (--resume-from) — 헌법 §Observability 정면 대응. | 신규 collector 가 idempotence 깨기 쉬움 — 각 collector PR 에 incremental 회귀 테스트 필수. |

**게이트 결과 (사전)**: ✅ 위반 없음. Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/001-roadmap/
├── plan.md              # 본 파일 (/speckit-plan 출력)
├── spec.md              # 위 스펙
├── research.md          # Phase 0 — 후술
├── data-model.md        # Phase 1 — 후술
├── quickstart.md        # Phase 1 — 후술
├── contracts/
│   ├── cli-contracts.md     # CLI 명령 schema
│   └── file-contracts.md    # jsonl/markdown file schema
└── tasks.md             # Phase 2 (/speckit-tasks — 본 명령 외 사이클)
```

추가로 본 roadmap 은 5개의 후속 spec 디렉터리를 *위임* 한다 (각 Phase 의 자체 specify → plan 사이클):

```text
specs/002-timeline-recall/        # FR-A1 + 일부 FR-A9
specs/003-feedback-loop/          # FR-A2 (+ FR-D1 일부 사전 작업)
specs/004-cost-observability/     # FR-A3, FR-A4, FR-A5
specs/005-daily-resilience/       # FR-A6, FR-A7, FR-A8
specs/006-raw-rag-hybrid/         # FR-B1, FR-B2, FR-X4 회귀 가드
specs/007-pass3-preview/          # FR-B3, FR-X2 강화
specs/008-draft-reply/            # FR-B4
specs/009-card-incremental/       # FR-B5
specs/010-collector-imessage/     # FR-C1
specs/011-collector-kakaotalk/    # FR-C2
specs/012-collector-gmail/        # FR-C3
specs/013-collector-voice/        # FR-C4
specs/014-profile-lifecycle/      # FR-D1, FR-D2, FR-D3
specs/015-decision-outcome/       # FR-D4, FR-D6
specs/016-multiturn-session/      # FR-D5
specs/017-menubar-app/            # FR-E1
specs/018-obsidian-plugin/        # FR-E2
specs/019-ios-shortcuts/          # FR-E3
```

### Source Code (repository root)

```text
src/synapse_memory/
├── cli.py                  # (수정) 신규 subcommand: feedback, cost, draft-reply, sessions
├── daily.py                # (대규모 수정) stage dependency + SKIP + --resume-from
├── llm/
│   ├── apfel.py            # (수정) cost emit hook
│   └── claude.py           # (수정) cost emit hook + meta prefix 후처리
├── storage/
│   ├── l0.py               # 변경 없음
│   └── sessions.py         # (신규) session jsonl read/write/rotate
├── collectors/
│   ├── claude_code/        # 변경 없음 (이미 동작)
│   ├── obsidian/           # 변경 없음
│   ├── imessage/           # (신규) Phase C
│   ├── kakaotalk/          # (신규) Phase C
│   ├── gmail/              # (신규) Phase C
│   └── voice/              # (신규) Phase C — faster-whisper
├── redaction/              # 변경 없음 (Pass3 preview 는 endpoints 측에서 처리)
├── clusters/               # 변경 없음
├── cards/
│   ├── project.py          # 변경 없음
│   ├── company.py          # 변경 없음
│   ├── auto_classify.py    # 변경 없음
│   ├── auto_generate.py    # 변경 없음
│   └── update.py           # (신규) FR-B5 incremental update
├── rag/
│   ├── embeddings.py       # 변경 없음
│   ├── indexer.py          # (수정) chunk indexer 추가 (FR-B1)
│   ├── chunker.py          # (신규) raw chunk split
│   ├── bm25.py             # (신규) BM25 보조 인덱스
│   ├── hybrid.py           # (신규) RRF 결합
│   └── vector_store.py     # 변경 없음
├── endpoints/
│   ├── ask.py              # (수정) --hybrid, --preview-prompt, --session
│   ├── me.py               # (수정) --timeline, --hybrid, --preview-prompt, draft-reply, outcome
│   └── session.py          # (신규) multi-turn 컨텍스트 로더
├── profile/
│   ├── extract.py          # (수정) validation_history, conflict detection
│   ├── decay.py            # (신규) FR-D2 confidence decay
│   └── conflicts.py        # (신규) FR-D3 모순 검출
├── feedback/               # (신규 모듈)
│   ├── events.py           # FeedbackEvent dataclass + writer/reader
│   └── apply.py            # 인덱싱 시 confidence 가중치 적용
└── cost/                   # (신규 모듈)
    ├── events.py           # CostEvent + emit/read
    └── summary.py          # cost summary 집계

tests/
├── feedback/               # (신규) test_feedback_*.py
├── cost/                   # (신규) test_cost_*.py
├── rag/                    # (확장) test_rag_chunker.py, test_rag_bm25.py, test_rag_hybrid.py
├── collectors/             # (확장) test_collector_imessage.py 등
├── endpoints/              # (확장) test_endpoints_timeline.py, test_endpoints_session.py
└── golden/                 # (확장) calibration_30.jsonl (gitignore), ndcg_eval_20.json

.github/workflows/
└── ci.yml                  # (신규) pytest + ruff + mypy

docs/
└── operations.md           # (신규) launchd, cost cap, 실패 로그 (assessment §I10)
```

**Structure Decision**: 기존 단일 `src/synapse_memory/` 패키지 구조 유지. 신규는 2개 최상위 서브패키지(`feedback/`, `cost/`) + 기존 서브패키지 내 신규 파일로만 확장. 모듈 경계가 헌법 §"Trust boundary inventory" 의 외부 LLM 노출 분류와 1:1 매핑 유지.

## Constitution Check (post-design re-check)

Phase 1 산출물(아래 §"Phase 1 산출물") 작성 후 재평가 결과:

| 원칙 | 재확인 결과 |
|---|---|
| I. Local-First & Privacy by Default | ✅ 신규 jsonl·OAuth 토큰 경로가 모두 L0 하위로 명시됨 (`contracts/file-contracts.md`). |
| II. Two-Pass Redaction (NON-NEGOTIABLE) | ✅ FR-B3 `--preview-prompt` 가 Pass 3 역할 수행. raw → external LLM 직송 경로는 데이터 모델·flow 어디에도 없음. |
| III. Test-First Discipline (NON-NEGOTIABLE) | ✅ FR-X3 가 PR 단위 테스트 강제. CI(FR-A8)가 P1 안에 포함되어 자동화. |
| IV. Conversation-Context-Aware Endpoints | ✅ `contracts/cli-contracts.md` 의 각 명령에 interactive/batch 분류 명시. |
| V. Reproducible Daily Pipeline & Observability | ✅ DailyReport·CostEvent·stage dependency 가 헌법 §"Observability" 의 모든 요건을 만족. |

**최종 게이트 결과**: ✅ 통과. Complexity Tracking 불필요.

## Phase 0 산출물 (research.md)

별도 파일 `specs/001-roadmap/research.md` 에 작성. 미해결 결정 7개 + 베스트 프랙티스 5개를 다룬다.

## Phase 1 산출물

`specs/001-roadmap/data-model.md`, `contracts/cli-contracts.md`, `contracts/file-contracts.md`, `quickstart.md`, 그리고 `CLAUDE.md` 의 `<!-- SPECKIT START -->` 마커 사이 plan 참조 갱신.

## Phase 2 (위임)

각 Phase 의 task breakdown 은 본 사이클 범위 외(`/speckit-tasks` 가 별도 호출). 그러나 위임 spec 디렉터리(specs/002~019) 목록은 본 plan §"Project Structure" 에 명시됨 — 각 디렉터리는 빈 폴더로만 생성하고 자체 `/speckit-specify <기능 설명>` 호출에서 채운다.

## Complexity Tracking

본 plan 의 헌법 게이트는 양쪽(pre·post) 모두 통과 — 정당화할 위반 사항 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (없음) | — | — |

---

## Implementation Sequencing Summary

| 마일스톤 | 기간 (추정) | 의존성 | 주요 게이트 |
|---|---|---|---|
| **v0.5 (Phase A)** P1 | 4~6주 | 헌법 v1.0.0, 기존 v0.4 | CI green, redaction F1 회귀 없음, daily 5분 유지 |
| **v0.6 (Phase B)** P2 | 6~8주 | v0.5 완료 (feedback 신호가 가중치 갱신 입력) | NDCG@5 +0.05, hybrid top-1 +20%p |
| **v0.7 (Phase C)** P3 | 8~12주 (collector 4개 병행) | v0.5 (cost 가시화 필수) | collector 격리, OAuth 토큰 0600 검증 |
| **v0.8 (Phase D)** P3 | 6~8주 | v0.5 feedback, v0.6 raw RAG, v0.7 data breadth | calibration follow-rate +15%p |
| **Phase E (Interface)** P4 | 병행 (각 2~4주) | v0.5 만 필요 (cost/daily report 시각화) | menubar 알림, plugin 패널 동작 |

**총 예상 기간**: v0.5 → v0.8 직렬 24~34주 (≈ 6~8개월), Phase E 병행 시 동일.

**병렬화 기회**:
- Phase B 의 FR-B4(draft-reply)·FR-B5(card update) 는 raw RAG 와 독립 → 병행 가능
- Phase C 의 4개 collector 는 서로 독립 → 4개 PR 병행
- Phase E 는 어느 단계에서나 시작 가능 (단, cost.jsonl 가 필수이므로 v0.5 이후 권장)

## 다음 단계

1. **본 plan + research.md / data-model.md / contracts/ / quickstart.md** 검토 후 first sub-feature 인 `/speckit-specify timeline 회상에 period_start 기반 정렬을 추가` 호출
2. → `specs/002-timeline-recall/` 가 생성되면 `/speckit-plan` 으로 코드-레벨 plan 작성
3. → `/speckit-tasks`, `/speckit-implement` 사이클로 진입
4. 각 sub-feature 머지 후 헌법 §"Versioning policy" 에 따라 patch (PATCH 미만) / minor (새 endpoint) bump
