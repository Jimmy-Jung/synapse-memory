# Feature Specification: Private 폴더 + 외부 AI 차단 + /sm:redact

**Feature Branch**: `0.10.0/feature/012-private-permissions`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "외부 ai가 읽을 수 없도록 claudeignore 등에 privatememory.md 같은 파일을 추가하고, 로컬 llm이 개인정보를 읽고 마스킹처리 혹은 안전하게 처리해서 외부 ai에게 정보를 전달하도록하는게 현재 구현되어있는 로컬llm을 활용할 수 있는듯"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 로컬에서 private 파일을 apfel로 redact해 외부 AI에 안전하게 전달 (Priority: P1)

사용자가 vault의 `90_System/Private/personalmemory.md` 같은 개인 메모를 외부 AI(Claude Code, Codex)에 직접 노출하지 않고, 로컬 LLM(apfel)으로 마스킹한 결과만 전달하고 싶을 때 `synapse-memory redact file <path>` 명령으로 한 번에 처리한다.

**Why this priority**: 사용자 요청의 핵심. 기존 3-pass redaction 인프라(`redact_full` 진입점)를 재사용하므로 구현 위험 낮음. 슬래시 호출 `/sm:redact <path>`로 일상 사용 가능.

**Independent Test**: 합성 PII가 있는 파일 1개를 `synapse-memory redact file /tmp/x.md` 호출 → stdout에 마스킹된 결과 출력. 원문 파일은 그대로.

**Acceptance Scenarios**:

1. **Given** PII(전화번호, 이메일, 회사명 등)가 포함된 markdown 파일, **When** `synapse-memory redact file <path>` 실행, **Then** stdout에 redacted 결과 출력, 종료 코드 0, 원본 파일 변경 없음
2. **Given** redactlist에 등록된 회사명이 포함된 파일, **When** redact 실행, **Then** 해당 단어가 placeholder로 마스킹됨
3. **Given** `--out <path>` 옵션, **When** 실행, **Then** stdout 대신 지정 경로에 redacted 파일 저장
4. **Given** 입력 파일이 존재하지 않음, **When** 실행, **Then** stderr 에러 메시지 + 종료 코드 2
5. **Given** apfel 미설치 환경, **When** 실행, **Then** Pass 1(regex)만 적용한 결과 출력 + stderr 경고

---

### User Story 2 - Claude Code 차단을 위한 vault Private 폴더 관례·설정 가이드 (Priority: P1)

신규 사용자가 vault에 `90_System/Private/` 폴더를 만들고 `.claude/settings.json`의 `permissions.deny`로 차단하면 Claude Code가 그 폴더 안 파일을 읽기/쓰기/검색할 수 없도록 만든다. 가이드는 `synapse-memory doctor` 또는 docs로 제공.

**Why this priority**: redact CLI(US1)와 함께 도입해야 의미가 살아남. private 파일이 실제로 외부 AI에 차단되지 않으면 redact 흐름이 무용지물.

**Independent Test**: vault의 `.claude/settings.json`에 deny 패턴 추가 후 Claude Code 세션에서 `Read(90_System/Private/x.md)` 시도 → 거부됨.

**Acceptance Scenarios**:

1. **Given** docs에 명시된 deny 패턴(`Read`, `Glob`, `Write` 셋 다), **When** 사용자가 vault `.claude/settings.json`에 적용, **Then** Claude Code의 Read/Glob/Write 셋 다 차단
2. **Given** `synapse-memory doctor` 실행, **When** Private 폴더 존재하지만 deny 설정 없을 때, **Then** 경고 출력 + 수정 명령 안내

---

### User Story 3 - Codex 격리 정책 가이드 (Priority: P2)

Codex CLI에는 `permissions.deny` 동등 기능이 없으므로 정책적 차단을 안내한다. AGENTS.md 헤더에 명시 + 작업 디렉터리를 vault 루트가 아닌 sub-folder로 분리하는 권장 패턴.

**Why this priority**: 사용자가 Codex를 vault 안에서 실행할 때만 발생. 비주류 시나리오지만 무시하면 false security.

**Independent Test**: docs에 명시된 패턴에 따라 `~/.codex/AGENTS.md` 또는 vault `AGENTS.md`에 Private 진입 금지 명시 후, Codex 세션이 그 지시를 인식하는지 확인 (수동).

**Acceptance Scenarios**:

1. **Given** vault 루트 `AGENTS.md`에 "Codex MUST NOT access 90_System/Private/" 라인 추가, **When** Codex 세션 시작, **Then** Codex가 해당 폴더에 자발적으로 진입하지 않음 (정책 준수)
2. **Given** 작업 디렉터리를 vault sub-folder(`10_Active/<project>/`)로 잡고 Codex 실행, **When** Codex가 상위 vault root를 탐색하려 함, **Then** sandbox 정책상 작업 디렉터리 밖 접근 차단 (Codex 기본 동작)

### Edge Cases

- redact file 호출 시 입력 파일이 매우 큼 (수 MB) → 청크 분할 또는 메모리 안전 처리. v0.10.x 한도는 단일 파일 최대 1 MB로 제한
- redactlist에 한국어 단어가 들어 있을 때 대소문자 무관 매치 → 기존 `redactlist.py` 동작 그대로 (이미 case-insensitive)
- Private 폴더에 텍스트가 아닌 파일(이미지, PDF 등)이 있을 때 → 텍스트 파일만 redact, 다른 형식은 skip + 경고
- 사용자가 deny 패턴 잘못 작성 (예: `Read(./90_System/Private)` — `**` 누락) → doctor가 보정 안내
- `.claude/settings.json`이 vault 루트가 아닌 다른 위치에 있을 때 → settings 로딩 우선순위 명시 (글로벌 < 프로젝트)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `synapse-memory redact file <path>` CLI subcommand under existing `redact` parser
- **FR-002**: `redact file` MUST read input file, apply existing `redact_full(text, env=apfel)` (Pass 1 + Pass 2), and print redacted text to stdout by default
- **FR-003**: `redact file` MUST support `--out <path>` option to write redacted result to a file instead of stdout
- **FR-004**: `redact file` MUST exit with code `2` when input path does not exist; `0` on success
- **FR-005**: `redact file` MUST gracefully fall back to Pass 1 only when apfel is unavailable (macOS < 26 or apfel binary missing), with a stderr warning. No silent skip of Pass 2
- **FR-006**: System MUST limit single-file input to 1 MB to prevent runaway memory. Larger files SHOULD return exit code 2 with guidance
- **FR-007**: System MUST skip binary files (image, PDF, etc.) with a stderr warning. Only text files (UTF-8 decodable) are processed
- **FR-008**: System MUST provide a slash command `/sm:redact <path>` in the Claude Code plugin marketplace that maps to `synapse-memory redact file <path>`
- **FR-009**: `synapse-memory doctor` MUST detect if `90_System/Private/` exists in vault, and if so check whether `vault/.claude/settings.json` includes `Read(./90_System/Private/**)` (and Glob/Write) in `permissions.deny`. Emit a warning when missing
- **FR-010**: System MUST provide documentation (docs/reference.md or new section) describing the recommended deny patterns and Private folder convention

### Key Entities *(include if feature involves data)*

- **Private file**: Markdown file under `vault/90_System/Private/`. Lifecycle: user-authored, may contain raw PII / 회사명 / 개인 사정. Never sent unredacted to external AI.
- **Redacted output**: stdout 또는 `--out` 파일. Pass 1 (regex) + Pass 2 (apfel) 결과 적용된 마스킹 텍스트. Placeholder convention 기존 `pass2.PASS2_PLACEHOLDERS` 그대로.
- **Vault permissions config**: `vault/.claude/settings.json` (Claude Code 차단), `vault/AGENTS.md` 헤더 (Codex 정책 안내). 둘 다 vault 측 자산, repo는 docs만 제공.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `synapse-memory redact file <path>` 호출 5초 이내 응답 (Pass 1 + Pass 2 합쳐서, 1 MB 미만 입력에 한해)
- **SC-002**: redact 통과한 출력에 redactlist 등록 단어가 단 1건도 남지 않음 (회귀 테스트로 검증)
- **SC-003**: deny 패턴 적용된 Claude Code 세션이 `Read(90_System/Private/**)` 호출 시 100% 거부 (수동 검증)
- **SC-004**: 신규 + 회귀 테스트 모두 통과 (`pytest` 847 + 신규 ≥ 5 = 852+)
- **SC-005**: `synapse-memory doctor` 가 Private 폴더 존재 + deny 누락 시 경고 출력 (회귀 테스트)

## Assumptions

- 사용자 vault는 이미 `90_System/` 디렉터리 컨벤션을 따른다 (PARA 기반)
- apfel은 macOS 26+ Apple Silicon에서만 동작. 그 외 환경에서는 Pass 1 only로 fallback이 합리적
- `.claudeignore`는 Claude Code 공식 매커니즘이 아니므로 만들지 않는다 (Spike 1 검증, 2026-05-17)
- Codex는 정책 기반(`AGENTS.md`)만 가능, 강제 차단 기능 없음. v0.10.x에선 docs 가이드로 한정
- Private 폴더 안 파일 redact는 의식적 호출 시점 (`/sm:redact`)에만 발생. daily 파이프라인은 Private 폴더를 자동으로 redact하지 않는다 (별도 feature로 분리 가능)
