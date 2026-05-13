# 구현 계획: Persona OS

**브랜치**: `010-persona-os` | **작성일**: 2026-05-13 | **명세**: [spec.md](./spec.md)  
**작성자**: JunyoungJung  
**입력**: `specs/010-persona-os/spec.md` 기능 명세

## 요약

Persona OS는 사용자의 대화와 첨부를 지속적으로 받아 말투, 선호, 판단 기준,
금지 영역을 검토 가능한 형태로 축적하는 local-first personal context layer다.
MVP는 "나를 완벽히 복제하는 모델"이 아니라 승인된 Persona claim과 근거를
관리하는 시스템으로 제한한다.

핵심 구현 방향은 다음과 같다.

- 스킬 표면은 `skills/persona-os/SKILL.md` 하나로 유지한다.
- CLI 표면은 `synapse-memory persona start/add/next/review/simulate` 다섯 개로 제한한다.
- raw 입력과 첨부 원본은 L0 private 영역에만 저장한다.
- vault에는 redacted summary, claim statement, evidence reference만 남긴다.
- `Profile.md`, `Voice.md`, `Boundaries.md`는 사용자가 승인한 claim만 반영한다.

## 기술 맥락

**언어/버전**: Python 3.11+ package, markdown vault files  
**주요 의존성**: 기존 `synapse_memory` package, YAML frontmatter, 기존 redaction/RAG/LLM 경계  
**저장소/파일 상태**: `~/.synapse/private/`, 선택된 Obsidian vault `90_System/AI/Persona/`  
**테스트**: pytest unit/CLI tests, file contract tests  
**대상 플랫폼**: Apple Silicon macOS, 기존 Synapse Memory 지원 환경  
**프로젝트 유형**: Python CLI/library + Obsidian markdown workflow  
**성능 목표**: `persona next/review`는 pending claim 200개 기준 1초 이내  
**제약**: local-first privacy, raw content vault 저장 금지, 승인 전 Profile 반영 금지  
**범위**: 단일 사용자 local workstation, vault 1개, Persona OS MVP command surface

## 현재 코드 기준 보정

- 기존 `Profile.md`와 `DecisionPatterns.md`는 backward compatible하게 유지한다.
- Persona OS는 기존 파일을 마이그레이션하거나 삭제하지 않는다.
- 기존 `/synapse-ask`, `/synapse-recall`, `/synapse-decide`, `/synapse-resume` 흐름은
  Persona OS MVP의 필수 변경 대상이 아니다.
- MVP에서는 skill 추가보다 CLI/data model/file contract를 먼저 고정한다.

## 헌법 검토

| 원칙 | 검토 결과 | 근거 / 완화 |
| --- | --- | --- |
| I. Local-First & Privacy by Default | 통과 | raw text와 첨부는 L0 private에만 저장한다. |
| II. Two-Pass Redaction | 통과 | vault-visible Persona claim은 redaction 이후 산출물만 허용한다. |
| III. Test-First Discipline | 통과 | file creation, non-overwrite, review flow, boundary refusal을 테스트한다. |
| IV. Conversation-Context-Aware Endpoints | 조건부 통과 | simulate는 accepted Persona context와 cited evidence만 사용한다. |
| V. Reproducible Daily Pipeline & Observability | 통과 | daily pipeline과 독립된 Persona workflow로 둔다. |

## 프로젝트 구조

### 이 feature의 문서

```text
specs/010-persona-os/
├── spec.md
└── plan.md
```

### 예상 source code 변경

```text
skills/
└── persona-os/
    └── SKILL.md

src/synapse_memory/
├── cli.py
└── persona/
    ├── __init__.py
    ├── files.py
    ├── evidence.py
    ├── claims.py
    ├── questions.py
    └── simulate.py

tests/
├── test_persona_files.py
├── test_persona_add.py
├── test_persona_review.py
├── test_persona_next.py
└── test_persona_simulate.py
```

**구조 결정**: `src/synapse_memory/persona/`를 새 domain module로 둔다.
CLI parsing은 `cli.py`에 연결하되, file IO, evidence 저장, claim 상태 전이,
question selection, simulate boundary check는 모듈로 분리한다.

## 마일스톤 계획

### M1 - Persona 파일 표면과 `persona start`

**목표**: `90_System/AI/Persona/`의 최소 파일 표면을 만들고 덮어쓰기 없이 시작한다.

**범위**:

- `Profile.md`, `Voice.md`, `Boundaries.md`, `Inbox.md` 생성.
- 기존 파일이 있으면 보존.
- pending claim 수와 다음 질문 1개 출력.
- vault 경로가 없으면 파일 생성 없이 설정 안내.

**테스트**:

- 빈 vault에서 4개 파일 생성.
- 기존 파일 non-overwrite.
- vault missing failure path.

### M2 - `persona add`와 evidence/claim inbox

**목표**: 텍스트와 지원 파일을 하나의 add command로 받아 pending claim 후보로 남긴다.

**범위**:

- text input, `--file` input, text+file batch 처리.
- raw input은 L0 private에 저장.
- vault에는 redacted summary와 claim candidate만 append.
- unsupported file type 안내.

**테스트**:

- raw content가 vault에 직접 쓰이지 않음.
- `Inbox.md` pending claim append.
- 동일 evidence batch provenance 유지.

### M3 - `persona review`

**목표**: pending claim을 사용자가 승인/거절해야만 Persona 진실원본에 반영한다.

**범위**:

- pending list 출력.
- `--accept <claim_id>`를 category별 target file로 반영.
- `--reject <claim_id> --reason` 상태 기록.
- conflict 표시와 반복 질문 방지 metadata 기록.

**테스트**:

- add 직후 Profile/Voice/Boundaries 불변.
- accept 후 target file 반영.
- reject reason 유지.

### M4 - `persona next`

**목표**: coverage gap 기반으로 다음 질문 1개를 제안한다.

**범위**:

- accepted claim coverage 계산.
- pending claim이 많으면 review 우선 안내.
- 최근 질문 반복 회피.

**테스트**:

- boundaries 부족 시 boundaries 질문 우선.
- pending threshold 초과 시 review 안내.
- repeated question 회피.

### M5 - `persona simulate`

**목표**: 승인된 Persona 자료와 cited evidence만으로 상황별 응답 초안을 만든다.

**범위**:

- accepted Persona context 로드.
- Boundaries check 우선.
- evidence 부족 시 답변 대신 추가 질문.
- 충분한 경우 response draft + claim id 출력.

**테스트**:

- 충분한 evidence에서 grounded response.
- 부족한 evidence에서 NeedMoreInfo.
- boundary violation에서 refusal/confirmation.

## 리스크 목록

| 리스크 | 영향 | 완화 |
| --- | --- | --- |
| 사용자가 추출 claim을 그대로 믿음 | 잘못된 자기 정보 고착 | pending -> review -> accept flow 강제 |
| raw attachment가 vault에 남음 | privacy violation | L0 private 저장과 redacted vault output 테스트 |
| skill/command 표면 증가 | 사용성 저하 | Persona OS skill 1개, CLI 5개 제한 |
| simulate가 그럴듯하게 꾸밈 | 신뢰 하락 | cited evidence 부족 시 질문으로 전환 |
| 기존 Profile/DecisionPatterns와 충돌 | backward compatibility 저하 | MVP에서는 읽기 context만 허용, migration 금지 |

## 헌법 검토 (설계 후 재확인)

| 원칙 | 결과 |
| --- | --- |
| I. Local-First & Privacy by Default | 통과 |
| II. Two-Pass Redaction | 통과 |
| III. Test-First Discipline | 통과 |
| IV. Conversation-Context-Aware Endpoints | 조건부 통과: simulate evidence citation 필요 |
| V. Reproducible Daily Pipeline & Observability | 통과 |

**최종 검토 결과**: 통과. 단, `persona simulate`는 근거 claim id와 boundary check를
테스트로 고정한 뒤 구현해야 한다.
