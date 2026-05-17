# Implementation Plan: Obsidian Graph 시각화 (P1+P2 only)

**Branch**: `0.13.0/feature/015-graph-viz` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)

## Summary

graph 시각화의 핵심 가치(노드 색상 그룹 + MOC 허브 + Dataview 의존성 안내)만 본 sprint에서 ship. US4 (Suggested wikilink)는 P3로 격하 — noise 양산 우려와 ROI 검증 부족 때문에 후속 결정.

## Constitution Check

| 원칙 | 결과 | 근거 |
|---|---|---|
| I. Local-First & Privacy | ✅ | 모든 파일 로컬. 외부 LLM 호출 없음. |
| II. Two-Pass Redaction | ✅ N/A | trust boundary 새로 없음. |
| III. Test-First Discipline | ✅ | node 태그 / MOC / doctor 모두 TDD. |
| IV. Conversation-Context-Aware | ✅ N/A | |
| V. Reproducible Pipeline | ✅ | daily 영향 없음 (FR-009: MOC 자동 트리거 X). |
| VI. Installation Consent Scoping | ✅ | MOC는 명시 호출만. doctor는 read-only. |

## Phase 1: Design

### Affected modules

| 파일 | 변경 |
|---|---|
| `src/synapse_memory/cards/*` (project/company 생성) | 수정: frontmatter `tags`에 `node/card` 추가 |
| `src/synapse_memory/profile/extract.py` `save_profile_update` | 수정: frontmatter `tags: [node/profile-update]` |
| `src/synapse_memory/daily.py` `render_daily_report` | 수정: frontmatter `tags: [node/daily-report]` |
| `src/synapse_memory/moc/__init__.py` | 신규: MOC generator (marker 패턴) |
| `src/synapse_memory/cli.py` | 수정: `moc` 서브커맨드 + doctor에 dataview 체크 등록 |
| `src/synapse_memory/doctor.py` | 수정: `diagnose_dataview_plugin(vault)` |
| `tests/test_node_tags.py` | 신규: 4 시나리오 (card / profile / daily / decision) |
| `tests/test_moc_generator.py` | 신규: 3 시나리오 (신규 생성 / marker 갱신 / 사용자 영역 보존) |
| `tests/test_doctor_dataview_check.py` | 신규: 3 시나리오 |
| `commands/moc.md`, `skills/moc/SKILL.md` | 신규 |
| `docs/reference.md` | 수정: "Obsidian Graph 시각화" 섹션 |

### TDD 순서

1. **Red**: node 태그 테스트 (4 시나리오)
2. **Green**: card / profile / daily frontmatter 패치
3. **Red**: doctor dataview 체크 (3 시나리오)
4. **Green**: `diagnose_dataview_plugin` + cmd_doctor 등록
5. **Red**: MOC generator (3 시나리오)
6. **Green**: `moc/__init__.py` + `cmd_moc` + 서브파서
7. docs + slash + skill
8. 전체 회귀 + release

## Complexity Tracking

위반 없음.
