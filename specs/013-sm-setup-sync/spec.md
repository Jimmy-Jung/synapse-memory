# Feature Specification: /sm:setup + /sm:sync — cross-project Profile marker

**Feature Branch**: `0.11.0/feature/013-sm-setup-sync`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "다른 플러그인들에서는 어떻게 처리하고있어? 그리고 Claude, Codex 등 여러 외부 ai에서 동일하게 동작해야해 + 새 프로젝트에서 sm:setup 같은 스킬을 추가해서 AGENTS.md, CLAUDE.md 같은 파일에 <!-- SYNAPSE-MEMORY START --> <!-- SYNAPSE-MEMORY END --> 같은 방법을 사용해서 추가하는건 어때?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 새 프로젝트에 sm 컨텍스트를 1회 등록 (Priority: P1)

사용자가 새 프로젝트 디렉터리에서 `synapse-memory setup` 명령을 한 번 실행하면, 그 프로젝트의 `AGENTS.md`(Codex가 읽음)와 `CLAUDE.md`(Claude Code가 읽음)에 `<!-- SYNAPSE-MEMORY START -->` … `<!-- SYNAPSE-MEMORY END -->` marker로 감싼 컨텍스트 블록이 추가된다. 이 블록은 vault Profile/Patterns 절대 경로와 핵심 요약(상위 N개 fact + M개 pattern)을 담는다. 외부 AI는 세션 시작 시 이 marker 안 내용을 자연스럽게 읽는다.

**Why this priority**: 기능 5의 핵심. 다른 프로젝트에서 sm 컨텍스트를 활용하는 첫 진입점.

**Independent Test**: 임시 디렉터리에서 `synapse-memory setup --target both`를 실행하면 `AGENTS.md`와 `CLAUDE.md`가 신규 생성되고 marker가 그 안에 들어가는지 확인. `~/.synapse/projects.yaml`에도 등록되는지.

**Acceptance Scenarios**:

1. **Given** AGENTS.md / CLAUDE.md가 둘 다 없음, **When** `setup --target both`, **Then** 두 파일 모두 신규 생성 + marker 삽입, 종료 코드 0
2. **Given** AGENTS.md가 이미 존재 (사용자 작성 내용 있음), **When** `setup --target agents`, **Then** AGENTS.md 파일 끝에 marker 블록 append, 기존 내용 보존
3. **Given** marker가 이미 있는 프로젝트, **When** `setup` 재실행, **Then** marker 사이 내용만 교체, 마커 바깥 보존 (idempotent)
4. **Given** `setup` 실행 후, **When** `~/.synapse/projects.yaml` 확인, **Then** 등록된 entry에 path, target, registered_at, last_sync, state 필드 존재
5. **Given** `setup --dry-run`, **When** 실행, **Then** 의도된 변경 출력만, 실제 파일 변경 0

---

### User Story 2 - 명시 호출로 등록된 프로젝트 marker 갱신 (Priority: P1)

vault Profile/Patterns가 바뀐 뒤 `synapse-memory sync` 명령으로 `~/.synapse/projects.yaml`에 등록된 **모든** 프로젝트의 marker 사이 내용을 일괄 갱신한다. `--current` 옵션으로 현재 디렉터리 프로젝트만 갱신할 수도 있다. 자동 트리거는 없음 (사용자 결정).

**Why this priority**: setup만 있고 sync가 없으면 marker가 stale해진다. 사용자가 결정한 명시 호출이 필수.

**Independent Test**: 두 개의 임시 프로젝트를 setup으로 등록 후 vault Profile.md를 임의로 수정. `synapse-memory sync` 호출 → 두 프로젝트 모두 marker 갱신 + last_sync 업데이트.

**Acceptance Scenarios**:

1. **Given** 2개 프로젝트 등록, **When** `sync` (옵션 없이), **Then** 둘 다 marker 갱신 + projects.yaml의 `last_sync` 업데이트
2. **Given** 등록된 프로젝트 path가 사라짐, **When** `sync` 실행, **Then** 해당 entry `state: stale` 표시 + 경고, 나머지는 정상 처리
3. **Given** `sync --current` (cwd 프로젝트만), **When** 실행, **Then** 현재 디렉터리 entry만 갱신
4. **Given** marker 사이를 사용자가 수동 편집한 프로젝트, **When** `sync` 실행, **Then** backup을 `~/.synapse/sync-backups/<hash>-<date>.md`에 보관 후 marker 교체

---

### User Story 3 - cross-AI 호환 (Claude / Codex 동시 동작) (Priority: P2)

같은 marker 블록을 Claude Code(`CLAUDE.md` 읽음)와 Codex(`~/.codex/AGENTS.md` + 프로젝트 `AGENTS.md` 읽음) 둘 다 동일하게 인식한다. 프로젝트 루트 `AGENTS.md`는 Codex 표준, `CLAUDE.md`는 Claude Code 표준이므로 양쪽 target 옵션이 필요.

**Why this priority**: Codex 또는 Claude Code 한쪽만 쓰는 사용자도 있고, 둘 다 쓰는 사용자도 있다. 양쪽 옵션 + both 옵션 모두 필요.

**Independent Test**: setup 실행 후 Codex와 Claude Code 세션을 각각 시작 → 둘 다 marker 내용을 자연스럽게 인지하는지 확인 (수동).

**Acceptance Scenarios**:

1. **Given** `setup --target claude`, **When** 실행, **Then** CLAUDE.md만 생성/수정, AGENTS.md는 손대지 않음
2. **Given** `setup --target agents`, **When** 실행, **Then** AGENTS.md만, CLAUDE.md 손대지 않음
3. **Given** `setup --target both` (기본값), **When** 실행, **Then** 둘 다 생성/수정

### Edge Cases

- 프로젝트가 git 리포가 아닐 때 → 그래도 동작 (`setup`은 `.git` 존재 가정 안 함)
- vault 경로를 사용자가 설정하지 않았을 때 → setup이 에러 + 안내 (`config.yaml` 점검 안내)
- marker 외부 라인이 매우 큰 파일 (수십 MB CLAUDE.md) → marker 사이만 교체 + 외부 보존, 처리는 그대로
- 잘못된 marker (START는 있는데 END가 없음) → setup이 파싱 에러로 종료 + 사용자 안내 (자동 수정 안 함, fail-closed)
- projects.yaml이 손상됨 → 백업 후 빈 registry 재생성 + 경고
- 동시에 두 터미널에서 `sync` 실행 → 파일 락 또는 atomic write로 충돌 방지

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `synapse-memory setup [--target {agents,claude,both}] [--dry-run]` CLI subcommand
- **FR-002**: `setup` MUST inject a block delimited by `<!-- SYNAPSE-MEMORY START -->` and `<!-- SYNAPSE-MEMORY END -->` into target file(s). If file doesn't exist, create it.
- **FR-003**: `setup` MUST register the cwd project in `~/.synapse/projects.yaml` with fields: `path`, `target`, `registered_at`, `last_sync`, `state`
- **FR-004**: `setup` MUST be idempotent: re-running replaces marker contents only, preserves surrounding text
- **FR-005**: `setup` MUST refuse to proceed if file has START without END (or vice versa), printing parsing error
- **FR-006**: System MUST provide `synapse-memory sync [--current]` CLI subcommand
- **FR-007**: `sync` (no flag) MUST refresh marker contents in ALL registered projects and update `last_sync`
- **FR-008**: `sync --current` MUST refresh only the cwd project (if registered)
- **FR-009**: `sync` MUST mark entries as `state: stale` when registered path no longer exists, without modifying that entry's other fields
- **FR-010**: `sync` MUST back up the existing marker block to `~/.synapse/sync-backups/<project-hash>-<ISO date>.md` before replacing, when the existing block differs from the canonical generated block
- **FR-011**: Marker contents MUST include: vault Profile.md absolute path, vault DecisionPatterns.md absolute path, "Quick reference" 상위 N개 fact (default N=5) + M개 pattern (default M=4), `/sm:recall`·`/sm:ask` 슬래시 안내 한 줄
- **FR-012**: `setup` and `sync` MUST NOT be auto-triggered by `daily` or any other command. Explicit user invocation only.

### Key Entities

- **Project registry**: `~/.synapse/projects.yaml`. Schema (`version: 1`, `projects: [{ path, target, registered_at, last_sync, state }]`). Lifecycle: setup adds entries, sync updates `last_sync`/`state`.
- **Marker block**: 파일 내부 `<!-- SYNAPSE-MEMORY START -->` … `<!-- SYNAPSE-MEMORY END -->` 사이 한 문단. canonical generator가 매번 같은 내용을 만들어 idempotent 보장. 사용자 수동 편집 시 backup 후 교체.
- **Backup**: `~/.synapse/sync-backups/<8-char-hash>-<YYYY-MM-DD>.md`. 사용자가 직접 정리 (synapse-memory가 자동 삭제 안 함).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `setup` 호출 1초 이내 완료 (vault Profile/Patterns 읽기 포함)
- **SC-002**: 두 번 setup 실행해도 파일 내용 동일 (byte-level idempotent)
- **SC-003**: 5개 프로젝트 등록 후 `sync` 호출 → 5개 모두 갱신, 1초 이내
- **SC-004**: 신규 테스트 통과 (`pytest` 858 + 신규 ≥ 10 = 868+)
- **SC-005**: Codex와 Claude Code 세션 각각에서 marker 내용 인식 확인 (수동 검증)

## Assumptions

- 사용자 vault에는 이미 `90_System/AI/Profile.md`와 `DecisionPatterns.md`가 있다 (없으면 setup이 에러 + 안내)
- `~/.synapse/`는 이미 존재 (다른 synapse-memory 명령이 만들어둠)
- AGENTS.md / CLAUDE.md는 markdown text, marker는 HTML comment 형식이라 마크다운 렌더링 시 보이지 않음
- 프로젝트별 자동 sync는 도입하지 않는다 (사용자가 명시 거부 — 2026-05-17 결정)
- marker 안 "Quick reference" 요약은 Profile/Patterns의 frontmatter나 상위 N개 항목에서 단순 추출. LLM 기반 요약 X (비용·결정론)
