# Implementation Plan: Cost Observability

**Branch**: `004-cost-observability` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/004-cost-observability/spec.md`

## Summary

Synapse Memory 의 Claude Code CLI / apfel 외부 호출이 끝날 때마다 로컬 private `cost.jsonl` 에 호출 메타데이터를 append-only 로 기록하고, `synapse-memory cost summary` 로 최근 N일 비용·토큰·elapsed 를 command 또는 model 기준으로 집계한다. 구현은 새 외부 의존성 없이 `cost/` 도메인 모듈, `llm/claude.py` / `llm/apfel.py` 호출 wrapper 계측, CLI subcommand, docs/slash shim 으로 구성한다.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: 기존 표준 라이브러리, `pydantic`, `chromadb`, `sentence-transformers`; 신규 외부 의존성 없음  
**Storage**: `~/.synapse/private/cost.jsonl`, 손상 tail backup `cost.jsonl.bak.<event_id>`  
**Testing**: pytest, ruff, mypy strict, redaction golden eval  
**Target Platform**: macOS 26 Tahoe + Apple Silicon  
**Project Type**: Python CLI/library  
**Performance Goals**: cost event append overhead ≤ 20ms per mocked call, 5,000 events summary ≤ 300ms  
**Constraints**: local-first, append-only event log, prompt/response 원문 저장 금지, logging failure 는 원래 명령 성공/실패를 바꾸지 않음, code change 는 test-first, redaction F1 회귀 없음  
**Scale/Scope**: 단일 사용자, cost event 0~50,000건, Claude/apfel 호출 경로 2개 wrapper 중심

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 계획상 준수 방식 | 위험 / 완화 |
|---|---|---|
| I. Local-First & Privacy by Default | cost log 는 `~/.synapse/private/` 하위에 0600/0700 권한으로만 기록한다. | prompt/response 원문이 실수로 들어갈 수 있음 → event schema 를 metadata-only 로 제한하고 golden test 로 원문 부재 검증. |
| II. Two-Pass Redaction | 이 feature 는 외부로 새 payload 를 보내지 않고 기존 Claude/apfel 호출을 관측만 한다. | cost logger 가 prompt 를 저장하면 위반 → file contract 에 금지 필드 명시, tests 에 민감 문자열 부재 검증. |
| III. Test-First Discipline | cost event model/writer/recovery/summary/CLI/wrapper 계측 테스트를 구현보다 먼저 배치한다. | wrapper 계측이 기존 호출 테스트를 깨뜨릴 수 있음 → 기존 mock 호환 테스트를 먼저 추가. |
| IV. Conversation-Context-Aware Endpoints | `cost summary` 는 batch endpoint 로 분류하여 TTY prompt 없이 실행한다. | `ask`/`me` interactive guard 와 무관하게 cost logging 은 내부 부수효과로만 동작. |
| V. Reproducible Daily Pipeline & Observability | cost event 는 append-only 이고 summary 는 결정적 집계로 daily report 의 기반 관측값을 제공한다. | 손상 로그가 daily 를 깨뜨릴 수 있음 → readable prefix 보존 + corrupt tail backup recovery. |

**게이트 결과 (사전)**: 통과. Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/004-cost-observability/
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
├── cli.py                         # cost summary subcommand 추가
├── cost/
│   ├── __init__.py
│   ├── events.py                  # CostEvent 생성·검증·append/recover/load
│   ├── pricing.py                 # provider/model token → USD best-effort 산정
│   └── summary.py                 # days/by 기준 결정적 집계
├── llm/
│   ├── claude.py                  # _run_claude 계측, envelope token/cost 추출
│   └── apfel.py                   # _run_apfel 계측, token heuristic/fallback
└── storage/
    └── l0.py                      # 기존 secure dir/file helper 재사용

tests/
├── test_cost_events.py
├── test_cost_summary.py
├── test_cost_cli.py
├── test_llm_claude.py
└── test_apfel.py

commands/
└── synapse-cost.md                # slash command compatibility surface

docs/
└── commands.md                    # CLI 문서 업데이트
```

**Structure Decision**: 비용 관측은 `feedback/` 과 같은 독립 도메인 경계로 `cost/` 를 둔다. 저장·복구 패턴은 `feedback/events.py` 의 append-only JSONL 방식을 재사용하되, schema 는 prompt/response 원문을 담을 수 없게 별도로 제한한다. 외부 호출 계측은 중복을 피하려고 `llm/claude.py` 와 `llm/apfel.py` 의 subprocess wrapper 직후에 배치한다.

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
| I. Local-First & Privacy by Default | 통과. 모든 신규 persistent 파일은 L0 private 하위이고 file contract 에 권한을 명시했다. |
| II. Two-Pass Redaction | 통과. 신규 외부 payload 없음. CostEvent 는 prompt/response/body/reason 필드를 금지한다. |
| III. Test-First Discipline | 통과. tasks 단계에서 event writer, summary, CLI, wrapper 계측 테스트를 구현보다 먼저 배치한다. |
| IV. Conversation-Context-Aware Endpoints | 통과. `cost summary` 는 batch endpoint 로 분류한다. |
| V. Reproducible Daily Pipeline & Observability | 통과. append-only log 와 deterministic aggregate 로 daily report 의 기반 관측값을 제공한다. |

**최종 게이트 결과**: 통과. Complexity Tracking 불필요.

## Complexity Tracking

위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
