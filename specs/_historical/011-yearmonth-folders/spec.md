# Feature Specification: MemoryInbox / DailyReports 년·월 폴더 구조

**Feature Branch**: `0.9.0/feature/011-yearmonth-folders`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "daily 스킬을 사용할때마다 쌓이는 파일들이 폴더구분없이 쌓이니 지저분해지는데, 년/월 기준으로 폴더를 구분이 필요"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 신규 daily 실행 시 년/월 폴더 자동 생성 (Priority: P1)

사용자가 `synapse-memory daily` 또는 `/sm:daily`를 실행하면 그날의 Profile 후보와 DailyReport가 자동으로 `{year}/{month:02d}/` 하위 폴더로 분류되어 저장된다. 사용자는 별도 설정 없이 처음부터 정돈된 vault 구조를 얻는다.

**Why this priority**: 매일 1회 실행되는 핵심 경로. 이게 동작하지 않으면 기능 가치가 0이다.

**Independent Test**: 빈 vault에서 `synapse-memory daily --quick` 1회 실행 → `90_System/AI/MemoryInbox/2026/05/Profile-2026-05-17.md`와 `90_System/AI/DailyReports/2026/05/2026-05-17.md`가 생성됨을 확인.

**Acceptance Scenarios**:

1. **Given** vault의 MemoryInbox 폴더가 비어 있을 때, **When** daily 실행, **Then** `MemoryInbox/2026/05/Profile-2026-05-17.md` 생성
2. **Given** vault의 DailyReports 폴더가 비어 있을 때, **When** daily 실행, **Then** `DailyReports/2026/05/2026-05-17.md` 생성
3. **Given** `2026/05/` 폴더가 이미 존재할 때, **When** 같은 달 두번째 daily 실행, **Then** 같은 폴더에 다른 날짜 파일 추가 (폴더 재생성 X, 기존 파일 보존)
4. **Given** 새 달로 진입한 날 (예: 2026-06-01), **When** daily 실행, **Then** `2026/06/` 폴더 자동 생성

---

### User Story 2 - 기존 flat 파일을 년/월 구조로 일괄 마이그레이션 (Priority: P1)

기존 사용자가 `synapse-memory migrate-folders`를 실행하면 vault의 flat한 `Profile-YYYY-MM-DD.md`와 `YYYY-MM-DD.md` 파일들이 모두 올바른 년/월 폴더로 이동된다. `--dry-run`으로 이동 대상을 미리 확인할 수 있다.

**Why this priority**: 기존 vault 사용자가 새 구조로 옮겨갈 수 있어야 한다. 이 마이그레이션 없이는 신규 daily만 새 구조로 가고 옛 파일은 영원히 flat한 채로 남는다.

**Independent Test**: 기존 vault 백업본에서 `synapse-memory migrate-folders --dry-run` → 이동 대상 리스트 출력. 실제 실행 후 모든 flat 파일이 정확한 년/월 폴더로 이동됐는지 확인.

**Acceptance Scenarios**:

1. **Given** `MemoryInbox/Profile-2026-04-23.md` flat 파일이 존재할 때, **When** `migrate-folders` 실행, **Then** `MemoryInbox/2026/04/Profile-2026-04-23.md`로 이동
2. **Given** `DailyReports/2026-05-17.md` flat 파일이 존재할 때, **When** `migrate-folders` 실행, **Then** `DailyReports/2026/05/2026-05-17.md`로 이동
3. **Given** flat 파일과 동일 경로의 년/월 폴더 파일이 모두 존재할 때 (충돌), **When** `migrate-folders` 실행, **Then** 이동 중단 + 충돌 보고. 사용자 결정 전엔 덮어쓰지 않음
4. **Given** `--dry-run` 플래그, **When** `migrate-folders --dry-run` 실행, **Then** 이동 대상 리스트 출력만, 실제 파일 변경 0건

---

### User Story 3 - dataview 쿼리 호환 유지 (Priority: P2)

vault에서 동작하던 기존 dataview 쿼리(`90_System/Home.md`, `90_System/AI/` 인덱스 등)가 년/월 폴더 구조로 변경된 후에도 정상 작동한다.

**Why this priority**: P1이 동작해도 dataview 쿼리가 깨지면 사용자가 매일 보는 대시보드가 빈 화면이 된다. 이건 회귀.

**Independent Test**: 마이그레이션 전 vault에서 dataview 결과 캡처 → 마이그레이션 후 동일 쿼리 결과 비교. 항목 수 일치, 항목 순서·내용 일치.

**Acceptance Scenarios**:

1. **Given** dataview가 `FROM "90_System/AI/MemoryInbox"` 같이 폴더 prefix만 지정할 때, **When** 마이그레이션 후 쿼리 실행, **Then** 하위 폴더 파일까지 모두 인덱싱 (dataview는 재귀 검색이 기본)
2. **Given** dataview 쿼리가 파일명 정규식으로 `Profile-YYYY-MM-DD.md` 매치할 때, **When** 마이그레이션 후, **Then** 매치 결과 동일

### Edge Cases

- 같은 날짜에 daily가 두 번 실행되면? → 두 번째 실행이 같은 파일을 덮어쓰는 기존 동작 유지 (변경 없음)
- 파일명이 `Profile-2026-05-17.md` 정규식에 안 맞는 변형(예: 수동으로 만든 `Profile-draft.md`)? → migrate에서 무시. `--report-unknown` 옵션으로 무시된 파일 리스트 출력
- vault 경로가 iCloud sync 중일 때 파일 이동 conflict? → mv가 실패하면 에러 메시지 + 해당 파일 skip, 나머지 진행. 부분 성공 보고
- migrate-folders를 두 번 실행? → 두 번째는 이동 대상 0건 (이미 모두 년/월 하위에 있음)
- 윤년·월말(2026-02-29 같은 케이스): 날짜 파싱은 ISO 표준 사용, 윤년은 datetime이 알아서 처리

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create `{vault}/90_System/AI/MemoryInbox/{YYYY}/{MM}/Profile-{YYYY-MM-DD}.md` for new daily Profile candidates (instead of flat `MemoryInbox/Profile-{YYYY-MM-DD}.md`)
- **FR-002**: System MUST create `{vault}/90_System/AI/DailyReports/{YYYY}/{MM}/{YYYY-MM-DD}.md` for new daily reports (instead of flat `DailyReports/{YYYY-MM-DD}.md`)
- **FR-003**: System MUST create intermediate year and month directories with `mkdir(parents=True, exist_ok=True)` semantics (idempotent)
- **FR-004**: Month folder name MUST be zero-padded 2 digits (`05`, not `5`)
- **FR-005**: System MUST provide `synapse-memory migrate-folders` CLI command to move existing flat files to year/month structure
- **FR-006**: System MUST support `--dry-run` flag on migrate-folders to print intended moves without actually moving files
- **FR-007**: System MUST detect filename collision before moving (flat file and year/month file with same name both exist) and refuse to overwrite. Report collision to user.
- **FR-008**: System MUST skip files whose names don't match expected `Profile-YYYY-MM-DD.md` / `YYYY-MM-DD.md` patterns; optional `--report-unknown` flag lists skipped files
- **FR-009**: Migrate-folders MUST be idempotent: second run after successful first run does nothing (0 moves)
- **FR-010**: Path generation MUST go through existing `VaultSystemAiFoldersConfig` so user can still override base folder names via `~/.synapse/config.yaml`
- **FR-011**: System MUST update `apply-profile` (future feature) and any other code that reads MemoryInbox candidates to scan recursively through year/month folders, not just flat-level

### Key Entities *(include if feature involves data)*

- **MemoryInbox candidate file**: `Profile-{ISO date}.md` with `type: profile_update` frontmatter. Lives at `90_System/AI/MemoryInbox/{YYYY}/{MM}/`. Lifecycle: `pending_review` → `applied`.
- **DailyReport file**: `{ISO date}.md` with daily pipeline stage summary. Lives at `90_System/AI/DailyReports/{YYYY}/{MM}/`. Read-only after creation.
- **Vault config**: `~/.synapse/config.yaml` `vault_folders.system.ai.{memory_inbox, daily_reports}` fields. Existing strings, no schema change required (year/month is derived at write time, not stored in config).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After `synapse-memory daily --quick` 1회 실행 on empty vault, expected file paths exist at `MemoryInbox/{YYYY}/{MM}/...` and `DailyReports/{YYYY}/{MM}/...` (100% pass rate in CI)
- **SC-002**: `synapse-memory migrate-folders --dry-run` on a vault with N flat files reports exactly N intended moves and 0 file mutations (verify with `git status` on vault git mirror if available, or before/after file count)
- **SC-003**: After actual `migrate-folders` execution, 0 files remain at flat level (excluding files matching `--report-unknown` exclusion list), 100% of expected files are at year/month paths
- **SC-004**: `pytest` regression suite passes including new tests for path generation and migration logic
- **SC-005**: Visual inspection: in Obsidian file explorer, `MemoryInbox/` and `DailyReports/` show year folders at top level, expandable into month subfolders, with files inside. No clutter at root.

## Assumptions

- 사용자 vault는 이미 `90_System/AI/MemoryInbox/`와 `DailyReports/` 폴더 관례를 따르고 있다 (기존 config 기본값 그대로 사용 중)
- 파일명은 항상 ISO 8601 날짜 포맷 `YYYY-MM-DD`로 시작한다. 다른 포맷의 파일은 사용자가 수동으로 만든 것으로 간주하고 migrate에서 무시
- iCloud sync는 일반적으로 mv 동작을 지원하지만, 동기화 race condition은 사용자 책임 영역. 마이그레이션 중에는 vault를 다른 기기에서 동시 편집하지 않을 것을 권장
- dataview는 폴더 prefix 지정 시 재귀 검색이 기본이므로 기존 쿼리는 대부분 깨지지 않는다 (User Story 3 검증 필요)
- 이번 feature는 MemoryInbox / DailyReports만 다룬다. Cards (`20_Reference/Projects/`, `Companies/`)는 일자가 아닌 lifecycle 기반이라 폴더 분리 대상에서 제외 (별도 의사결정 필요시 후속 feature)
- migrate-folders는 1회성 도구다. 향후 v0.9.0 이후 사용자는 처음부터 새 구조로 시작하므로 migrate를 호출할 필요 없음. 단, 도구는 idempotent하게 남겨둬서 잘못된 위치에 파일이 생겼을 때 복구 가능
