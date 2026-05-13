# 구현 계획: Persona OS

> **Status**: SUPERSEDED
> **Replaced by**: `~/.claude/plans/1-linked-fox.md`
> **Date**: 2026-05-13
> **Reason**: 기존 `profile/` 모듈과의 중복 발견 + wedge 재정의 (외부 자료 ingest + design-project). `me` 와 `persona` namespace 통합. 본 plan 의 5-CLI / 4-file / persona module 구조 거부, `me` → `persona` rename + recipe 확장으로 대체.

**브랜치**: `010-persona-os` | **작성일**: 2026-05-13 | **명세**: [spec.md](./spec.md)  
**작성자**: JunyoungJung  
**입력**: `specs/010-persona-os/spec.md` 기능 명세

## 요약

Persona OS 는 사용자의 답변과 첨부 자료를 지속적으로 받아 말투, 선호, 판단 기준, 금지 영역을 검토 가능한 markdown 기반 Persona 자료로 축적한다. 구현은 기능 표면을 의도적으로 작게 유지한다: `skills/persona-os/SKILL.md` 하나, `synapse-memory persona {start,add,next,review,simulate}` 다섯 CLI 명령, vault 파일 네 개(`Profile.md`, `Voice.md`, `Boundaries.md`, `Inbox.md`)만 MVP 범위로 둔다.

기술 접근은 기존 Synapse Memory 원칙을 재사용한다. 원본 텍스트와 지원 첨부는 `~/.synapse/private/` 아래 L0 evidence batch 로 저장하고, vault에는 redaction을 통과한 claim 후보와 승인된 Persona claim만 기록한다. AI가 추출한 후보는 승인 전까지 simulation에 영향을 주지 않는다.

## 기술 맥락

**언어/버전**: Python 3.11+ package
**주요 의존성**: 기존 `synapse_memory` CLI, vault detector, L0 storage, redaction, LLM provider abstraction, markdown files
**저장소/파일 상태**: raw evidence는 `~/.synapse/private/persona/`, 사용자 검토/승인 자료는 `<vault>/90_System/AI/Persona/`
**테스트**: pytest unit/CLI/contract tests, LLM 호출은 mock 또는 deterministic extractor로 격리
**대상 플랫폼**: Apple Silicon macOS 26 Tahoe 이상, 기존 Synapse Memory platform floor 유지
**프로젝트 유형**: Python CLI/library + Obsidian markdown workflow + single Codex/Claude skill
**성능 목표**: `persona next`와 `persona review`는 pending claim 200개 기준 1초 이내, `persona start`는 fixture vault에서 1초 이내
**제약**: local-first privacy, two-pass redaction, 승인 전 Persona 반영 금지, Persona-specific skill 1개 제한, MVP CLI command 5개 제한
**범위**: 단일 사용자, 단일 vault, text/markdown attachment MVP, PDF는 명확한 unsupported 안내 후 후속 feature로 분리

## 헌법 검토

*검토 기준: Phase 0 조사 전 통과해야 하며, Phase 1 설계 후 다시 확인한다.*

| 원칙 | 검토 결과 | 근거 / 완화 |
| --- | --- | --- |
| I. Local-First & Privacy by Default | 통과 | raw PersonaEvidence는 L0 private storage에만 저장하고, vault-visible 파일에는 redacted summary와 claim만 쓴다. |
| II. Two-Pass Redaction | 통과 | 외부 LLM으로 가는 extraction/simulation prompt는 기존 redaction pipeline 이후의 텍스트만 사용한다. Redaction 결과가 비면 LLM 호출을 차단한다. |
| III. Test-First Discipline | 통과 | 구현 tasks는 RED tests부터 시작한다. 최소 테스트 축은 skeleton 생성, non-overwrite, pending→accepted, boundary refusal, raw leak 방지다. |
| IV. Conversation-Context-Aware Endpoints | 통과 | `persona add/next/review/simulate`는 interactive endpoint로 분류하고 `_interactive_guard()`를 적용한다. `persona start`는 파일 skeleton setup 성격이지만 다음 질문을 출력하므로 동일 guard 정책을 적용한다. |
| V. Reproducible Daily Pipeline & Observability | 통과 | daily pipeline ordering은 변경하지 않는다. Persona OS는 별도 CLI flow이며 idempotent file skeleton 생성과 deterministic markdown append 규칙을 가진다. |
| VI. Installation Consent Scoping | 통과 | installer setup consent 범위와 무관하다. Persona claim 승인과 운영 단계 메모리 쓰기는 계속 명시적 `persona review --accept`가 필요하다. |

**Post-design 재검토**: Phase 1 산출물 기준으로 위 게이트는 유지된다. Complexity Tracking 항목은 없다.

## 프로젝트 구조

### 이 feature의 문서

```text
specs/010-persona-os/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── cli-contracts.md
    └── file-contracts.md
```

### 예상 source code 변경

```text
skills/
└── persona-os/
    └── SKILL.md                         # Persona OS 단일 skill surface

src/synapse_memory/
├── cli.py                               # persona subparser 연결
└── persona/
    ├── __init__.py
    ├── schema.py                        # PersonaEvidence / PersonaClaim / Coverage
    ├── files.py                         # vault Persona markdown skeleton + managed sections
    ├── evidence.py                      # text/file input -> L0 private evidence batch
    ├── extract.py                       # redacted evidence -> PersonaClaim 후보
    ├── review.py                        # pending claim list/accept/reject
    ├── questions.py                     # coverage gap -> next question
    └── simulate.py                      # accepted Persona context -> grounded response

tests/
├── test_persona_files.py
├── test_persona_evidence.py
├── test_persona_review.py
├── test_persona_questions.py
├── test_persona_simulate.py
└── test_persona_cli.py
```

**구조 결정**: Persona OS는 기존 `profile/` 모듈을 직접 확장하지 않고 `persona/` vertical slice로 둔다. 이유는 기존 `Profile.md`/`DecisionPatterns.md` backward compatibility를 유지하면서, 새 승인 모델과 파일 surface를 독립적으로 테스트하기 위해서다. 단, L0 storage, redaction, LLM provider, vault detection은 기존 모듈을 재사용한다.

## Phase 0 산출물

[research.md](./research.md)를 참조한다.

## Phase 1 산출물

- [data-model.md](./data-model.md)
- [contracts/cli-contracts.md](./contracts/cli-contracts.md)
- [contracts/file-contracts.md](./contracts/file-contracts.md)
- [quickstart.md](./quickstart.md)
- Agent context: root [AGENTS.md](../../AGENTS.md) SPECKIT marker를 이 plan으로 갱신

## 마일스톤 계획

### M1 - Persona file skeleton 및 단일 skill

**목표**: 사용자가 `persona start` 한 번으로 Persona OS의 최소 파일 구조와 다음 질문을 볼 수 있다.

**범위**:

- `skills/persona-os/SKILL.md` 추가.
- `src/synapse_memory/persona/files.py` 추가.
- `persona start` CLI subcommand 추가.
- 기존 파일 non-overwrite 및 부분 누락 파일 복구.
- 기본 질문 fallback 제공.

**테스트**:

- 빈 fixture vault에서 4개 Persona 파일 생성.
- 기존 `Profile.md`가 있을 때 덮어쓰지 않음.
- Persona OS 관련 skill 파일이 하나만 존재.

**머지 가치**: 사용자가 Persona OS를 시작할 수 있고, 유지보수 표면이 작다는 계약이 코드에 고정된다.

### M2 - Evidence add 및 pending claim inbox

**목표**: 텍스트/markdown evidence를 L0에 보관하고 redacted PersonaClaim 후보를 `Inbox.md`에 추가한다.

**범위**:

- `persona add` CLI subcommand 추가.
- text input 및 `.txt`/`.md` file input 지원.
- unsupported extension은 fail-fast.
- evidence batch를 `~/.synapse/private/persona/evidence.jsonl`에 append.
- deterministic local rule 또는 mocked LLM boundary로 claim 후보 생성.
- `Inbox.md` managed section append.

**테스트**:

- text add 후 vault-visible 파일에 raw text가 그대로 쓰이지 않음.
- file add 후 private_ref만 vault에 남음.
- unsupported PDF는 명확한 안내와 non-zero exit.
- redaction 결과 0바이트면 LLM 호출 없음.

**머지 가치**: 사용자는 대화와 첨부를 꾸준히 누적할 수 있고, 승인 전에는 Persona가 바뀌지 않는다.

### M3 - Review accept/reject flow

**목표**: pending claim을 사용자가 승인/거절하고, 승인된 claim만 `Profile.md`, `Voice.md`, `Boundaries.md`에 반영한다.

**범위**:

- `persona review` CLI subcommand 추가.
- pending claim 목록 출력.
- `--accept <claim_id>` 및 `--reject <claim_id> --reason <text>` 지원.
- category 기반 target file routing.
- rejected/conflicted claim 상태 보존.

**테스트**:

- accept 전에는 Profile/Voice/Boundaries 변경 없음.
- accept 후 category별 target file에 provenance 포함.
- reject 후 다음 질문에서 같은 claim 반복 방지.
- conflict 상태는 accepted material을 덮어쓰지 않음.

**머지 가치**: Persona OS의 핵심 안전 경계인 승인 기반 진실원본 흐름이 동작한다.

### M4 - Coverage 기반 next question

**목표**: `persona next`가 현재 부족한 Persona 영역을 기준으로 질문 1개를 제안한다.

**범위**:

- `PersonaCoverage` 계산.
- pending claim threshold 적용.
- 최근 질문 반복 회피를 위한 lightweight question history.
- category별 기본 질문 bank.

**테스트**:

- Boundaries가 비어 있으면 금지/추측 금지 질문 우선.
- pending claim이 threshold 이상이면 review-first 안내.
- 최근 질문과 동일한 질문 반복 방지.

**머지 가치**: 사용자가 한 번짜리 설문이 아니라 지속적인 보강 루프를 경험한다.

### M5 - Accepted Persona simulation

**목표**: `persona simulate "<상황>"`이 승인된 Persona 자료만 사용해 근거 있는 응답 또는 추가 질문을 출력한다.

**범위**:

- accepted Persona context loader.
- boundary check.
- evidence sufficiency check.
- LLM prompt composition with claim ids.
- last_answer metadata 기록은 가능하면 기존 storage 재사용.

**테스트**:

- pending claim은 simulation prompt에 포함되지 않음.
- accepted boundary가 금지한 상황은 refusal.
- evidence 부족 시 답변 대신 next question 출력.
- 충분한 evidence가 있으면 claim id 포함.

**머지 가치**: Persona OS가 실제로 "나라면 어떻게 말할지/판단할지"를 안전하게 시뮬레이션한다.

## 의존 그래프

```text
M1 skeleton + skill
  └─> M2 add evidence + inbox
        └─> M3 review accept/reject
              ├─> M4 next question
              └─> M5 simulation
```

## 리스크 목록

| 리스크 | 영향 | 완화 |
| --- | --- | --- |
| PersonaClaim 추출이 과신을 만든다 | 잘못된 자기 정보가 승인될 수 있음 | pending 기본값, claim id/provenance, accept 전 simulation 미사용. |
| raw text가 vault-visible 파일에 새는 회귀 | privacy breach | contract test로 raw phrase absence 검증, redaction empty면 LLM 차단. |
| skill/command 표면이 커짐 | 사용성 저하와 유지보수 증가 | MVP는 skill 1개, CLI 5개를 FR로 고정. |
| PDF 첨부 기대와 MVP 범위 차이 | 사용자 혼란 | quickstart/contract에서 PDF unsupported를 명확히 안내하고 후속 feature로 분리. |
| 기존 Profile.md와 Persona/Profile.md 중복 | 혼란 | MVP는 기존 파일 read-only context로만 취급하고 migration 금지. |
| LLM 기반 conflict detection 비용/불안정성 | flaky tests | MVP conflict는 exact/near-duplicate 및 category-level rule 기반으로 시작, LLM conflict는 후속. |

## Complexity Tracking

헌법 위반 또는 정당화가 필요한 복잡성 없음.
