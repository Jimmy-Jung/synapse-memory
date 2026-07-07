# Research: Daily Resilience

## R1. Stage dependency representation

- **Decision**: `DailyStage` 를 ordered tuple 로 정의하고 각 stage 가 `required_for` 대신 `requires` 를 가진다.
- **Rationale**: 실행 가능 여부를 판단할 때 현재 stage 가 의존하는 upstream 을 직접 확인하는 쪽이 단순하다. downstream skip reason 은 실패한 upstream 이름으로 계산할 수 있다.
- **Alternatives considered**:
  - `required_for` adjacency list 만 저장: downstream 탐색이 필요해 resume/only/skip 과 결합할 때 복잡하다.
  - hard-coded if chain 유지: 새 stage 추가 시 skip/resume 규칙이 흩어진다.

## R2. Failure handling semantics

- **Decision**: 한 stage 가 실패해도 runner 는 즉시 중단하지 않고, 선택된 나머지 stage 를 dependency 상태에 따라 `skipped` 또는 실행으로 판정한 뒤 최종 exit code 1 을 반환한다.
- **Rationale**: 사용자는 실패 stage 뿐 아니라 downstream 영향 범위를 보고 재개 범위를 결정해야 한다. summary completeness 가 운영성을 높인다.
- **Alternatives considered**:
  - 첫 실패 즉시 중단: 빠르지만 어떤 단계가 영향 받았는지 알 수 없다.
  - 실패 후에도 모든 stage 실행: upstream 산출물이 없는 generate/index 같은 stage 에서 2차 오류가 생긴다.

## R3. Resume behavior

- **Decision**: `--resume-from <stage>` 는 target 이전 stage 를 `skipped` 상태로 기록하고 target 부터 dependency 판단을 다시 시작한다.
- **Rationale**: resume 범위가 stdout/DailyReport 에 명확히 드러나고, 사용자가 앞 단계가 재실행되지 않았음을 확인할 수 있다.
- **Alternatives considered**:
  - target 이전 stage 를 결과에서 생략: 실행 범위는 짧아 보이지만 감사 가능성이 낮다.
  - 이전 stage 를 success 로 간주: 실제 실행하지 않은 작업을 성공으로 표시해 observability 원칙에 어긋난다.

## R4. DailyReport write policy

- **Decision**: daily 종료 시 가능한 한 DailyReport 를 작성하되, report write failure 는 stage failure 를 덮어쓰지 않는다.
- **Rationale**: report 는 관측성 산출물이지만 pipeline 자체의 진짜 실패 원인보다 우선하면 안 된다.
- **Alternatives considered**:
  - report 실패 시 항상 exit 1: 모든 stage 성공 후 report 만 실패한 경우에는 맞지만, 기존 stage 실패 원인을 가릴 수 있다.
  - report 실패를 완전히 무시: 사용자가 report 누락을 알 수 없다.

## R5. CI scope

- **Decision**: GitHub Actions 는 Python setup 후 `python3 -m pytest tests/ -W ignore::DeprecationWarning`, `uvx ruff check ...`, `python3 -m mypy --strict ...` 를 실행한다.
- **Rationale**: 프로젝트의 현재 로컬 검증 명령과 일치시키면서 apfel/Claude/Codex 실제 binary 없이 mock 기반 테스트가 통과하는지 확인한다.
- **Alternatives considered**:
  - 실제 apfel/Claude 설치: CI secret/환경 의존이 생겨 local-first 원칙과 맞지 않는다.
  - pytest만 실행: ruff/mypy gate 가 main 밖에서만 발견된다.
