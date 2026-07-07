# Feature Specification: Obsidian Graph 시각화 — node 태그 + MOC + Suggested wikilink

**Feature Branch**: `0.13.0/feature/015-graph-viz`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "daily로 쌓이는 데이터를 obsidian의 graph로 내 세컨브레인을 시각적으로 확인해볼 수 있어야해. 어떤식으로 구현할 수 있을지 브레인스토밍 필요. 이 기능이 필요한 이유는 내 세컨브레인을 직접 탐방하면서 개선이 필요한 부분을 찾아서 수정할 수 있게 하기 위함"

## Context (spike 결과 반영)

2026-05-17 검증:
- 사용자는 graph view를 적극 사용 중 (`90_System` colorGroup 직접 설정, force simulation 파라미터 튜닝됨, 마지막 active leaf가 graph view) — ROI 검증됨
- 자동 wikilink는 noise 양산 위험 — cluster 분류가 LLM 기반이라 잘못된 link로 graph가 더 어수선해질 수 있음 → "Suggested" 별도 섹션으로 분리, 사용자가 채택해야 link로 승격
- Dataview 플러그인은 MOC 동적 인덱스에 필요. 사용자 vault에는 이미 설치돼 있음 (Home.md에서 사용 확인). 신규 사용자는 미설치 가능 → doctor 체크 + fallback 안내

## User Scenarios & Testing *(mandatory)*

### User Story 1 - node 태그 규약 (Priority: P1)

생성된 Card / Profile candidate / DailyReport / DecisionPattern 후보 파일 frontmatter에 `#node/card`, `#node/profile-update`, `#node/daily-report`, `#node/decision-pattern` 태그를 자동 부착한다. 사용자는 Obsidian Graph 설정에서 그룹 색상을 한 번 분리하면 노드 유형별 색상이 자동으로 적용된다.

**Why this priority**: 가장 작은 변경으로 가장 큰 시각적 가치. wikilink/MOC 미도입 상태에서도 graph 색상 그룹화 가능.

**Independent Test**: synthetic vault에 daily 1회 실행 → 신규 생성된 Card·Profile·DailyReport frontmatter `tags`에 해당 `node/*` 포함 확인.

**Acceptance Scenarios**:

1. **Given** synthetic cluster, **When** `generate_project_card` / `generate_company_card` 호출, **Then** 생성 파일 frontmatter `tags`에 `node/card` 포함
2. **Given** save_profile_update 호출, **Then** 후보 파일 frontmatter `tags`에 `node/profile-update` 포함
3. **Given** write_daily_report 호출, **Then** 리포트 frontmatter `tags`에 `node/daily-report` 포함

---

### User Story 2 - MOC.md 자동 생성 (Priority: P1)

`90_System/AI/MOC.md` 파일을 daily 마지막 단계에서 (또는 별도 명령으로) 자동 생성·갱신한다. dataview query로 동적 인덱스: Cards, Profile updates, Daily reports, Decision patterns 각각 N개씩 최신순.

**Why this priority**: graph viz 진입점. 사용자가 "전체 노드를 빠르게 둘러보기" 위한 허브.

**Independent Test**: synthetic vault + 신규 명령 `synapse-memory moc` → `90_System/AI/MOC.md` 생성, dataview 블록 4개 포함.

**Acceptance Scenarios**:

1. **Given** vault에 신규 Card / Profile / DailyReport 존재, **When** `synapse-memory moc` 실행, **Then** MOC.md 신규 생성 + `TABLE FROM "20_Reference/Projects"` 같은 dataview 블록 포함
2. **Given** MOC.md 이미 존재 (사용자 편집), **When** 재실행, **Then** dataview 블록 사이만 갱신, 사용자 편집 부분은 marker로 보존 (013 sprint marker 패턴 재사용)
3. **Given** Dataview 미설치 환경, **When** MOC.md 열람, **Then** dataview 블록 자리에 "Dataview 플러그인 필요" 안내 텍스트 (fallback) — 실제 dataview 호출은 못 하지만 사용자가 어떻게 설치하는지 알 수 있음

---

### User Story 3 - Dataview 플러그인 존재 doctor 체크 (Priority: P2)

`synapse-memory doctor`가 vault `.obsidian/community-plugins.json`을 검사해 Dataview가 활성화돼 있는지 확인. 미설치/미활성 시 ⚠ 경고 + 설치 안내.

**Why this priority**: MOC의 dynamic 쿼리가 작동하려면 필요. 사용자가 doctor 한 번만 돌리면 알게 됨.

**Independent Test**: synthetic `.obsidian/community-plugins.json` 두 케이스 — dataview 포함 / 미포함 → diagnose 함수가 OK / WARN 반환.

**Acceptance Scenarios**:

1. **Given** `.obsidian/community-plugins.json`에 `"dataview"` 포함, **When** doctor 실행, **Then** OK 출력
2. **Given** 미포함, **When** doctor 실행, **Then** WARN + 설치 안내
3. **Given** `.obsidian/community-plugins.json` 자체가 없음, **When** doctor 실행, **Then** WARN (Obsidian이 vault에 한 번도 안 열렸을 가능성)

---

### User Story 4 - Suggested wikilink (Priority: P3)

Card 생성 직후 같은 cluster의 다른 Card들을 본문 `## Suggested links` 섹션에 wikilink로 제안한다. 본문 자동 삽입(자동 link)은 하지 않는다 — 사용자가 Obsidian에서 직접 채택할 때 link로 승격된다는 의미.

**Why this priority**: noise 양산 우려로 P3로 격하. 우선 node 태그 + MOC로 graph가 충분히 풍부해지면 그 후 추가 고려.

**Independent Test**: 합성 cluster (3 Cards) → 첫 Card의 frontmatter/본문에 다른 2 Card wikilink가 "Suggested" 섹션에 들어 있음 확인.

**Acceptance Scenarios**:

1. **Given** 3 Card 동일 cluster, **When** generate, **Then** 각 Card 본문 끝 `## Suggested links` 섹션에 나머지 2개 wikilink
2. **Given** cluster에 Card 1개만, **When** generate, **Then** "Suggested links" 섹션 자체 생략 (빈 섹션 X)

### Edge Cases

- vault `.obsidian/` 디렉터리 없음 (Obsidian 한 번도 안 열림) → doctor가 SKIPPED 또는 WARN으로 처리
- MOC.md 파일이 너무 큼 (사용자가 추가한 dataview 블록 다수) → marker 패턴으로 sm 영역만 격리
- Dataview 미설치 환경 → MOC fallback 텍스트, daily는 정상 동작 (graph 색상만 동작)
- 동일 cluster 내 Card 이름에 wikilink 깨질 만한 특수 문자 → escape 또는 alias 사용
- 이미 `node/*` 태그가 frontmatter에 있는 파일 → 중복 추가 안 함

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `generate_project_card` / `generate_company_card` MUST add `node/card` to frontmatter `tags`
- **FR-002**: `save_profile_update` MUST add `node/profile-update` to frontmatter `tags`
- **FR-003**: `write_daily_report` MUST add `node/daily-report` to frontmatter `tags`
- **FR-004**: System MUST provide `synapse-memory moc [--vault PATH]` CLI subcommand to generate/refresh `90_System/AI/MOC.md`
- **FR-005**: MOC.md MUST contain dataview blocks (TABLE / LIST queries) for Projects, Companies, Profile updates, Daily reports
- **FR-006**: MOC.md MUST use marker pattern (`<!-- SYNAPSE-MEMORY-MOC START/END -->`) so user-added content outside markers is preserved
- **FR-007**: MOC.md MUST include a fallback note when Dataview is not installed (e.g., "이 페이지는 Dataview 플러그인이 필요합니다")
- **FR-008**: `synapse-memory doctor` MUST diagnose Dataview plugin presence via `<vault>/.obsidian/community-plugins.json`
- **FR-009**: MOC generation MUST NOT be auto-triggered by daily (Constitution VI). 별도 호출 `synapse-memory moc` 또는 슬래시 `/sm:moc`로만.
- **FR-010** (P3): Card 생성 시 같은 cluster의 다른 Card wikilink를 본문 `## Suggested links` 섹션에 포함 (P3 — 본 sprint MVP 밖, 후속 결정)

### Key Entities

- **Node-tagged file**: vault markdown 파일 with `node/*` tag. Card / Profile candidate / DailyReport / DecisionPattern 후보 모두 해당.
- **MOC**: `90_System/AI/MOC.md`. marker로 감싼 sm 영역 (dataview 블록 + 안내) + 사용자 자유 편집 영역.
- **Dataview presence**: vault `.obsidian/community-plugins.json` 의 배열에 `"dataview"` 포함 여부.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 신규 daily 실행 후 생성된 Card / Profile / DailyReport frontmatter에 해당 `node/*` 태그 100% 포함 (회귀 테스트)
- **SC-002**: `synapse-memory moc` 호출 → MOC.md 생성, dataview 블록 4개 이상 포함 (회귀 테스트)
- **SC-003**: `synapse-memory doctor` Dataview 체크 — 활성화·미설치·.obsidian 부재 3 케이스 모두 적절한 상태 출력 (회귀 테스트)
- **SC-004**: 신규 + 회귀 테스트 통과 (`pytest` 879 + 신규 ≥ 7 = 886+)
- **SC-005**: Obsidian Graph view에서 `#node/card`, `#node/profile-update` 등 그룹 색상 분리 가능 (사용자 수동 검증)

## Assumptions

- 사용자 vault는 이미 Dataview 플러그인 설치돼 있음 (`90_System/Home.md`에서 사용 중 확인). 신규 사용자 대상으로만 doctor 안내.
- node 태그는 frontmatter `tags` 배열에 단순 추가. 기존 태그는 보존.
- MOC marker는 `<!-- SYNAPSE-MEMORY-MOC START/END -->` — 013 sprint의 `<!-- SYNAPSE-MEMORY START/END -->` 와 구분 (다른 도메인)
- US4 (Suggested wikilink)는 본 sprint 범위 외. 본 sprint는 P1+P2까지만 ship — node 태그 + MOC + doctor 체크.
- daily에서 자동 MOC 갱신은 안 함 (Constitution VI). 사용자가 `/sm:moc` 또는 `synapse-memory moc` 호출.
