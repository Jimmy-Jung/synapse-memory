# Research: Cost Observability

## R1. Cost event 위치

- **Decision**: Claude 는 `llm/claude.py::_run_claude`, apfel 은 `llm/apfel.py::_run_apfel` 직후에서 기록한다.
- **Rationale**: 두 함수가 실제 subprocess boundary 이므로 성공/실패/timeout/elapsed 를 한 곳에서 관측할 수 있다. 상위 endpoint 마다 중복 계측하면 `ask`, `me`, `daily`, `card generate`, `profile extract` 가 빠질 위험이 커진다.
- **Alternatives considered**:
  - CLI command handler 에서만 기록: library API 직접 호출과 daily 내부 호출이 누락된다.
  - endpoint 별 기록: 중복이 많고 실패 경로를 빠뜨리기 쉽다.

## R2. command 식별

- **Decision**: wrapper 는 optional `command` 값을 받되, 미지정 시 환경변수 `SYNAPSE_COMMAND` 또는 `"unknown"` 으로 기록한다. CLI handler 는 실행 전 command family 를 설정한다.
- **Rationale**: wrapper 수준에서는 어떤 CLI 명령에서 호출됐는지 모른다. 명시 인자를 모든 기존 call site 에 추가하면 변경 범위가 커지므로 환경 컨텍스트 fallback 을 둔다.
- **Alternatives considered**:
  - stack inspection: 취약하고 테스트가 어렵다.
  - 모든 `complete()` 호출에 command 필수화: type-safe 하지만 PR 범위와 회귀 위험이 커진다.

## R3. token / usd 산정

- **Decision**: Claude envelope 에 token/cost 관련 필드가 있으면 우선 사용하고, 없으면 입력은 local `estimate_tokens` heuristic 으로, 출력은 결과 텍스트 길이 heuristic 으로 추정한다. apfel 은 local-only 로 `usd=0`, `pricing_source="local_unpriced"` 를 기록한다.
- **Rationale**: Claude Code CLI envelope 형식은 버전별 차이가 있고, apfel 은 로컬 FoundationModels 호출이라 USD 과금이 없다. summary 는 정확 비용과 추정 비용을 모두 표시할 수 있어야 한다.
- **Alternatives considered**:
  - 비용이 없는 event 는 기록하지 않음: elapsed/call count 관측 가치가 사라진다.
  - 외부 가격표 fetch: local-first 원칙과 재현성을 해친다.

## R4. 손상 로그 복구

- **Decision**: `feedback/events.py` 와 같은 readable prefix 보존 + unreadable tail backup 방식을 사용한다.
- **Rationale**: JSONL 은 append 중단/전원 종료 시 tail 손상이 가장 흔하다. 정상 prefix 를 버리지 않고 다음 append/summary 를 계속할 수 있어야 daily 관측이 깨지지 않는다.
- **Alternatives considered**:
  - 손상 발견 시 전체 실패: batch summary/daily report 를 불필요하게 깨뜨린다.
  - 손상 줄 무시만 수행: 증거가 사라져 감사 가능성이 떨어진다.

## R5. slash command 표면

- **Decision**: `commands/synapse-cost.md` 는 compatibility shim 으로 추가하되, 장기 canonical surface 는 CLI와 docs다.
- **Rationale**: 프로젝트 정책상 `commands/` 는 legacy slash-entry compatibility surface 다. 비용 요약은 Claude/Codex 안에서 자주 확인할 수 있어 shim 가치는 있다.
- **Alternatives considered**:
  - CLI 문서만 추가: 기존 plugin/slash 사용 흐름과 맞지 않는다.
