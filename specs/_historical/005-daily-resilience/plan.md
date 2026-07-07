# Implementation Plan: Daily Resilience

**Branch**: `005-daily-resilience` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/005-daily-resilience/spec.md`

## Summary

Synapse Memory 의 `daily` 파이프라인을 명시적 stage graph 로 바꾸고, stage 실패 시 dependent stage 를 SKIP 처리하며, `--resume-from <stage>` 로 실패 지점부터 재개할 수 있게 한다. 실행 결과는 stdout summary 와 vault DailyReport markdown 에 동일한 stage status 로 남긴다. 마지막으로 GitHub Actions CI 를 추가해 PR/main 에서 pytest, ruff, mypy 를 mock 기반으로 실행한다.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: 기존 표준 라이브러리, `pytest`, `ruff`, `mypy`; 신규 외부 런타임 의존성 없음  
**Storage**: Vault `<vault>/90_System/AI/DailyReports/YYYY-MM-DD.md`, 기존 `~/.synapse/private/cost.jsonl` 읽기  
**Testing**: pytest, ruff, mypy strict, redaction golden eval  
**Target Platform**: macOS 26 Tahoe + Apple Silicon  
**Project Type**: Python CLI/library  
**Performance Goals**: dependency/skip planning overhead ≤ 10ms, DailyReport generation ≤ 100ms for one run, CI ≤ 5 minutes on GitHub runner  
**Constraints**: `daily` 는 batch endpoint 로 TTY prompt 없음, raw external payload 우회 없음, run result 는 deterministic, code change 는 test-first, redaction F1 회귀 없음  
**Scale/Scope**: 단일 사용자, daily stages 6~8개, DailyReport 1개/day, CI 는 local-only binaries 없이 mock suite 통과

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 계획상 준수 방식 | 위험 / 완화 |
|---|---|---|
| I. Local-First & Privacy by Default | DailyReport 는 사용자의 vault system area 에만 기록하고 raw content 를 포함하지 않는다. | stage summary 에 파일 본문이나 prompt 가 들어갈 수 있음 → summary 는 counters/status/path basename 수준으로 제한한다. |
| II. Two-Pass Redaction | 신규 외부 LLM payload 를 만들지 않고 기존 daily stage 내부 redaction 경로를 유지한다. | report 작성 중 raw sample 을 넣으면 위반 → DailyReport contract 에 raw/body/prompt 금지 명시. |
| III. Test-First Discipline | stage dependency, resume, CLI validation, report rendering, CI workflow 검증 테스트를 구현보다 먼저 tasks 에 배치한다. | 기존 `tests/test_daily.py` 가 dry-run 중심이라 통합 부족 → mock stage registry 기반 테스트를 추가한다. |
| IV. Conversation-Context-Aware Endpoints | `daily` 는 batch endpoint 로 유지하고 `_interactive_guard()` 를 추가하지 않는다. | `--resume-from` 오류가 prompt 로 바뀌면 automation break → argparse/handler 는 즉시 exit code 2 반환. |
| V. Reproducible Daily Pipeline & Observability | 모든 stage 결과에 status/elapsed/summary/skip reason 을 남기고 DailyReport 로 영구화한다. | report 실패가 원래 failure 를 가릴 수 있음 → report write failure 는 별도 warning/result 로 남기고 primary exit semantics 유지. |

**게이트 결과 (사전)**: 통과. Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/005-daily-resilience/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-contracts.md
│   └── file-contracts.md
└── tasks.md
```

### Source Code (repository root)

```text
src/synapse_memory/
├── daily.py                       # stage graph, resume, skip, DailyReport rendering
├── cli.py                         # daily --resume-from wiring and summary output
├── cost/
│   └── summary.py                 # existing summary reader reused for est USD
└── collectors/cards/rag/profile   # existing daily stage implementations reused

tests/
├── test_daily.py                  # stage graph/resume/skip/report tests
└── test_daily_cli.py              # CLI validation and exit code tests

.github/workflows/
└── ci.yml                         # pytest + ruff + mypy

docs/
└── commands.md                    # daily options and recovery examples
```

**Structure Decision**: 새 package 를 만들지 않고 `daily.py` 내부에 stage orchestration 모델을 둔다. daily 는 이미 stage별 도메인 모듈을 호출하는 composition layer 이므로, `DailyStage`, `StageResult`, `DailyResult` 를 같은 파일에 두는 것이 SRP 에 맞다. CLI 는 인자 검증과 exit code 만 담당하고, stage dependency/resume 판단은 `daily.py` 에 집중한다.

## Phase 0 산출물

See [research.md](./research.md).

## Phase 1 산출물

- [data-model.md](./data-model.md)
- [contracts/cli-contracts.md](./contracts/cli-contracts.md)
- [contracts/file-contracts.md](./contracts/file-contracts.md)
- [quickstart.md](./quickstart.md)

## Constitution Check (post-design re-check)

| 원칙 | 재확인 결과 |
|---|---|
| I. Local-First & Privacy by Default | 통과. DailyReport 는 local vault 에만 기록되며 raw prompt/body 를 금지한다. |
| II. Two-Pass Redaction | 통과. 외부 payload 경로를 새로 만들지 않고 기존 daily stage 내부 redaction 흐름을 보존한다. |
| III. Test-First Discipline | 통과. tasks 에 RED 테스트를 구현 전 배치한다. |
| IV. Conversation-Context-Aware Endpoints | 통과. `daily` 는 batch endpoint 로 남고 prompt 없이 실패한다. |
| V. Reproducible Daily Pipeline & Observability | 통과. stage status, skip reason, elapsed, report 를 명시적 contract 로 둔다. |

**최종 게이트 결과**: 통과. Complexity Tracking 불필요.

## Complexity Tracking

위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
