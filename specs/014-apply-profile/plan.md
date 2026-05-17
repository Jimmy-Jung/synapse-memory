# Implementation Plan: /sm:apply-profile

**Branch**: `0.12.0/feature/014-apply-profile` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)

## Summary

이 sprint는 **CLI 코드가 최소**다. 핵심은 슬래시 커맨드 prompt template (`commands/apply-profile.md`)이 AI에게 항목 파싱·AskUserQuestion 흐름·파일 편집을 지시한다. CLI는 보조 명령 `synapse-memory list-pending-profiles` 1개만 추가 — recursive scan으로 pending 후보 발견. `commands/daily.md`는 종료 후 apply 흐름 제안 instruction 추가.

## Technical Context

**Language/Version**: Python 3.11+ (CLI), Markdown (슬래시 prompt)
**Primary Dependencies**: 기존 `folders.find_candidate_files` 재사용 (011 sprint 산출물)
**Testing**: pytest (CLI 보조), 슬래시 흐름은 수동 검증
**Performance**: list-pending은 vault scan 1초 이내

## Constitution Check

| 원칙 | 결과 | 근거 |
|---|---|---|
| I. Local-First & Privacy | ✅ | 모든 파일 로컬, 외부 LLM 호출 없음 |
| II. Two-Pass Redaction | ✅ N/A | trust boundary 새로 안 만듦 |
| III. Test-First Discipline | ✅ | CLI list-pending TDD |
| IV. Conversation-Context-Aware | ✅ N/A | |
| V. Reproducible Pipeline | ✅ | apply는 명시 호출, daily에서 자동 진입은 사용자 yes 후에만 |
| VI. Installation Consent Scoping | ✅ | FR-008: 자동 강제 없음 |

## Phase 1: Design

### Affected modules

| 파일 | 변경 |
|---|---|
| `src/synapse_memory/cli.py` | 수정: `cmd_list_pending_profiles` + 서브파서 |
| `tests/test_cli_list_pending_profiles.py` | 신규: 3 시나리오 |
| `commands/apply-profile.md` | 신규: slash prompt 핵심 |
| `commands/daily.md` | 수정: 종료 후 apply 흐름 안내 |
| `skills/apply-profile/SKILL.md` | 신규 |
| `docs/reference.md` | 수정: apply-profile 섹션 |

### CLI 인터페이스

```
$ synapse-memory list-pending-profiles [--vault PATH] [--json]
```

출력 (기본):
```
2026-05-13 — /Users/.../MemoryInbox/2026/05/Profile-2026-05-13.md
2026-05-15 — /Users/.../MemoryInbox/2026/05/Profile-2026-05-15.md
```

JSON 모드: `[{"date": "2026-05-13", "path": "...", "status": "pending_review"}, ...]` — 슬래시 prompt가 파싱하기 좋게.

종료 코드: 0 항상 (vault 없으면 2).

### 슬래시 prompt 흐름 (`commands/apply-profile.md`)

1. `!`synapse-memory list-pending-profiles --json``로 후보 목록 받기
2. date 인자에 해당하는 경로 선택 (없으면 가장 최근)
3. 후보 파일 Read → ProfileFact·DecisionPattern bullet 라인 추출 (markdown 파싱)
4. 4개씩 묶어 AskUserQuestion (Yes / No / Edit)
5. "Edit" 선택 항목은 별도 AskUserQuestion으로 새 문구 입력 받음
6. 승인분만 `Profile.md` (해당 카테고리) / `DecisionPatterns.md` (`## Approved Patterns`)에 Edit으로 추가
7. 후보 파일 frontmatter `status: applied` + `applied_date: <오늘>` 갱신

### TDD 순서

1. **Red**: `test_cli_list_pending_profiles.py` (3 시나리오 — recursive scan, applied 제외, JSON 모드)
2. **Green**: `cmd_list_pending_profiles` 구현
3. slash prompt + skill + docs 작성
4. 회귀

## Project Structure

```text
specs/014-apply-profile/{spec,plan,tasks}.md

src/synapse_memory/cli.py             # [수정] cmd_list_pending_profiles
tests/test_cli_list_pending_profiles.py # [신규]

commands/
├── apply-profile.md                  # [신규] 핵심 slash prompt
└── daily.md                          # [수정] 종료 후 apply 흐름 안내

skills/apply-profile/SKILL.md         # [신규]
docs/reference.md                     # [수정] apply-profile 섹션
```

## Complexity Tracking

위반 없음. 슬래시 prompt 안에 AskUserQuestion 분할 로직(4개씩)을 instruction으로 남기는 게 핵심.
