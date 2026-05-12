# Implementation Plan: Timeline Recall (시간축 회상)

**Branch**: `002-timeline-recall` | **Date**: 2026-05-12 | **Spec**: `specs/002-timeline-recall/spec.md`
**Input**: Feature specification from `specs/002-timeline-recall/spec.md`

## Summary

`me what-did-i-think` 의 결과를 cosine distance 가 아닌 **시간순(`period_end desc`, 동률 시 `created desc`)** 으로 재정렬하고, 분기/월 그룹 헤더와 함께 표시하는 변경. 신규 모듈은 만들지 않고 `endpoints/me.py` 의 단일 함수 흐름에 *재정렬 + 그룹화 단계* 를 삽입한다. RAG retrieve 자체는 변경 없음(임베딩·top-K 동일). ChromaDB 가 이미 metadata 에 `period_end / created / last_reviewed / status` 를 색인하고 있으므로 (`rag/indexer.py:135,139,140,154,155`) **새 인덱싱이 필요 없다**.

전체 변경 면적:
- `src/synapse_memory/endpoints/me.py` — 새 함수 4개(`_resolve_sort_ts`, `_sort_by_time`, `_group_by_quarter`, `_format_timeline_output`) + `what_did_i_think()` 시그니처 확장
- `src/synapse_memory/cli.py` — `--timeline`, `--by {time|distance}`, `--limit` argparse 옵션 + 충돌 검증
- `tests/test_endpoints_me.py`·`tests/test_endpoints_me_extra.py` — 회귀 가드
- `tests/test_endpoints_me_timeline.py` — 신규 15 케이스
- `tests/golden/timeline_recall/synthetic_30.json` — 30 쿼리 골든셋 (synthetic)
- `commands/synapse-recall.md` — `$ARGUMENTS` 안내 갱신 (선택)

## Technical Context

**Language/Version**: Python 3.11+ (헌법 §Platform floor)
**Primary Dependencies**: 기존 — `chromadb` (metadata 그대로 사용), `pydantic`·`pyyaml` (Card 로딩). 신규 의존 0건.
**Storage**: 읽기 전용. ChromaDB 검색 결과 metadata 만 소비. 디스크 영구 저장 없음 (FR-015).
**Testing**: 기존 pytest. 신규 — `test_endpoints_me_timeline.py`, `tests/golden/timeline_recall/synthetic_30.json`.
**Target Platform**: macOS 26 Tahoe + Apple Silicon (변경 없음)
**Project Type**: CLI library 의 endpoints 모듈 내부 변경 (single project structure)
**Performance Goals**: post-retrieve 정렬 ≤ 200 ms @ 500 Cards (SC-002). top-K 가 ChromaDB 단계에서 이미 작아지므로 (기본 8~20) 실제 정렬 부담은 미미.
**Constraints**:
- `--timeline` 미지정 호출의 결과·순서·인용 텍스트가 100% 회귀 없이 동일해야 함 (FR-013, SC-004)
- 외부 LLM 으로 보내는 prompt 는 기존 `redact_full()` 경로 그대로 (FR-016, 헌법 §II)
- ChromaDB 결과 metadata 가 일부 누락된 Card 가 있어도 graceful 폴백 (Edge Case)
**Scale/Scope**:
- 영향 코드 면적: 단일 함수 + CLI 옵션 3개 + 테스트 ~15건 + golden 30 row
- 사용자 가시 변경: 새 CLI flag — `--timeline`, `--by {time|distance}`, `--limit N`

## Constitution Check

*GATE: Phase 0 진입 전 + Phase 1 design 후 두 차례 재평가.*

| 원칙 | 본 plan 의 준수 방식 | 위반 위험 / 완화책 |
|---|---|---|
| I. Local-First & Privacy by Default | 본 변경은 retrieve 결과 metadata 만 소비. raw 접근 없음. 새 파일/네트워크 호출 없음. | 위반 위험 없음. |
| II. Two-Pass Redaction (NON-NEGOTIABLE) | 외부 LLM 으로 가는 prompt 는 기존 `endpoints/me.py:_build_prompt()` 경로 그대로. timeline 헤더("## 2024 Q3" 등)가 prompt 에 포함될 경우에도 Card body 는 이미 redacted. | timeline 헤더 자체에 PII 없음 (분기 라벨만). 새 unit test 로 prompt 안에 raw fragment 가 없음을 assert. |
| III. Test-First Discipline (NON-NEGOTIABLE) | FR-001 → FR-017 각각에 최소 1개 unit test (총 17개 FR → 15개 케이스). 골든셋 회귀 1건. Red→Green→Refactor. | timeline 정렬 알고리즘이 단순해 over-test 위험. 골든셋 30 row 가 핵심 회귀 자산. |
| IV. Conversation-Context-Aware Endpoints | `me what-did-i-think` 은 기존부터 *대화형*. `cli.py:cmd_me_what_did_i_think:350` 이 이미 `_interactive_guard("me what-did-i-think", "recall")` 호출. 본 변경은 분류·가드 정책을 건드리지 않음 (FR-014). | 신규 옵션이 가드 우회 경로를 만들 위험 없음. |
| V. Reproducible Daily Pipeline & Observability | `daily` 파이프라인 영향 없음. 정렬은 retrieve 시점 ad-hoc 계산이라 idempotence 자명. | 위반 위험 없음. |

**게이트 결과 (사전)**: ✅ 위반 없음. Complexity Tracking 비어 있음.

## Project Structure

### Documentation (this feature)

```text
specs/002-timeline-recall/
├── plan.md              # 본 파일 (/speckit-plan 출력)
├── spec.md              # 위 스펙
├── research.md          # Phase 0 — 후술
├── data-model.md        # Phase 1 — 후술 (transient entity 만)
├── quickstart.md        # Phase 1 — 후술
├── contracts/
│   └── cli-contracts.md     # `me what-did-i-think` 신규 옵션 schema
├── checklists/
│   └── requirements.md  # 기존 (15/15 통과)
└── tasks.md             # Phase 2 (/speckit-tasks 가 별도 호출)
```

### Source Code (repository root) — 단일 프로젝트 구조 유지

```text
src/synapse_memory/
├── cli.py                  # (수정)
│   ├── cmd_me_what_did_i_think (line 349~)
│   │   └─ argparse 옵션 추가: --timeline, --by {time,distance}, --limit
│   └─ 충돌 검증 (--timeline + --by distance → exit 1)
└── endpoints/
    └── me.py               # (수정)
        ├── what_did_i_think() (line 230~) — 시그니처 확장: by, limit
        ├── _resolve_sort_ts(card_metadata, today)   # (신규 private)
        ├── _sort_by_time(citations)                 # (신규 private)
        ├── _group_by_quarter(citations)             # (신규 private)
        └── _format_timeline_output(groups)          # (신규 private)

tests/
├── test_endpoints_me.py           # (수정) 기존 distance 케이스 보강 — FR-013 회귀 가드
├── test_endpoints_me_timeline.py  # (신규) 15 케이스
│   ├── test_timeline_basic_sort         (FR-002)
│   ├── test_period_end_null_active      (FR-003)
│   ├── test_period_end_null_inactive    (FR-004)
│   ├── test_company_card_uses_last_reviewed (FR-005)
│   ├── test_quarter_group_header        (FR-006)
│   ├── test_month_subheader             (FR-007)
│   ├── test_single_result_no_header     (FR-008)
│   ├── test_by_time_alias               (FR-009 일부)
│   ├── test_by_distance_explicit        (FR-009 일부)
│   ├── test_conflict_timeline_and_by_distance  (FR-009)
│   ├── test_limit_default_and_override  (FR-010)
│   ├── test_empty_result_message        (FR-011)
│   ├── test_all_meta_null_fallback      (FR-012)
│   ├── test_distance_regression_default (FR-013, SC-004)
│   └── test_no_raw_in_prompt            (FR-016, 헌법 II)
└── golden/
    └── timeline_recall/
        └── synthetic_30.json    # (신규) 30 쿼리 × 평균 5건, Kendall τ 평가용
```

**Structure Decision**: 기존 패키지 구조 유지. 신규 디렉터리·패키지 없음. 모든 변경이 `endpoints/me.py` 1 파일 + `cli.py` argparse 보강 + 테스트 추가에 한정.

## Constitution Check (post-design re-check)

`research.md`·`data-model.md`·`contracts/cli-contracts.md`·`quickstart.md` 작성 후 재평가:

| 원칙 | 재확인 결과 |
|---|---|
| I. Local-First | ✅ 새 파일·네트워크 호출 0건. |
| II. Two-Pass Redaction | ✅ 정렬·그룹화는 metadata 만 소비. prompt 본문은 기존 redacted Card body 그대로. |
| III. Test-First | ✅ 15개 FR-mapped test + 골든셋 회귀로 RGR cycle 명확. |
| IV. Endpoint 분류 | ✅ `_interactive_guard("me what-did-i-think", "recall")` 호출 유지. |
| V. Idempotence/Observability | ✅ daily 영향 없음. 정렬은 stateless. cost.jsonl(FR-A3, v0.5 별건) 도입 시 본 명령 호출은 1 cost event 만 emit (변경 없음). |

**최종 게이트 결과**: ✅ 통과. Complexity Tracking 비어 있음.

## Phase 0 산출물 (research.md)

별도 파일 `specs/002-timeline-recall/research.md` 에 작성. 본 feature 가 결정해야 할 사항 5건 — 부모 plan 의 R1 을 본 feature 맥락으로 확장:

1. `period_end` 폴백 우선순위 (R1 확장)
2. `YYYY-MM` 입력의 *월 말일* 정규화 정책
3. 분기 라벨 포맷 (`2024 Q3` vs `2024-Q3` vs `Q3 2024`)
4. limit 기본값 (`20` 채택 근거)
5. distance 폴백 시 user-facing 메시지 톤

## Phase 1 산출물

- `specs/002-timeline-recall/data-model.md` — transient entity (`TimelineGroup`, `CardWithMeta`) 만. 디스크 schema 없음.
- `specs/002-timeline-recall/contracts/cli-contracts.md` — `me what-did-i-think` 의 신규 옵션 schema + exit code 정책.
- `specs/002-timeline-recall/quickstart.md` — feature 단독 데모 (가짜 vault 3 Card → timeline 출력 검증).
- `CLAUDE.md` `<!-- SPECKIT START -->` 마커 본 plan 파일로 갱신.

## Phase 2 (위임)

`/speckit-tasks` 가 본 plan 을 입력으로 task breakdown (`tasks.md`) 생성. 본 사이클 범위 외.

## Complexity Tracking

위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (없음) | — | — |

---

## Implementation Order (TDD 흐름)

1. **테스트 작성** (RED) — `test_endpoints_me_timeline.py` 15케이스 + 골든셋 30 row → 모두 실패 확인.
2. **`endpoints/me.py` 보강** (GREEN) — `_resolve_sort_ts`, `_sort_by_time`, `_group_by_quarter`, `_format_timeline_output` 추가. `what_did_i_think()` 가 `by` 인자에 따라 분기.
3. **`cli.py` 보강** (GREEN) — argparse 옵션 추가, 충돌 검증, `cmd_me_what_did_i_think` 가 새 인자를 endpoint 로 전달.
4. **회귀 가드** (GREEN) — `--timeline` 미지정 호출이 기존 골든 출력과 100% 일치 검증.
5. **REFACTOR** — 4개 private 함수의 docstring·type hint 정리. mypy strict 통과.
6. **문서** — `commands/synapse-recall.md` 옵션 안내 추가, `docs/commands.md` 의 회상 섹션 보강.
7. **PR** — 헌법 §"Spec Kit flow" PR 체크리스트(research B4) 첨부.

## 다음 단계

본 plan 검토 후 `/speckit-tasks` 호출 → `tasks.md` 생성 → `/speckit-implement` 호출로 RED→GREEN→REFACTOR 진입.
