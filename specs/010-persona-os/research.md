# 조사 기록: Persona OS

**기능**: 010-persona-os
**작성일**: 2026-05-13
**작성자**: JunyoungJung

## R-1 - Skill surface: `persona-os` 하나만 유지

- **결정**: Persona OS는 `skills/persona-os/SKILL.md` 하나만 추가한다.
- **근거**: 사용자는 스킬 간소화를 명시적으로 요구했다. 기존 Synapse Memory skill도 CLI mapping과 안전 원칙 중심으로 동작하므로, Persona OS도 skill을 구현 상세가 아니라 "언제 쓰고 어떤 CLI를 호출하는가"만 담는 얇은 surface로 두는 것이 맞다.
- **대안 검토**:
  - `persona-interview`, `persona-review`, `persona-simulate` 등 여러 skill: 기능 발견성은 높아 보이지만 사용자가 어떤 skill을 써야 하는지 헷갈리고 plugin packaging 표면이 커져 제외.
  - 기존 `skills/synapse-memory/SKILL.md`에만 추가: 파일 수는 줄지만 Persona OS의 제품 개념이 묻히고, skill이 너무 커져 제외.

## R-2 - CLI command surface: 다섯 명령으로 제한

- **결정**: MVP CLI는 `persona start`, `persona add`, `persona next`, `persona review`, `persona simulate`만 제공한다.
- **근거**: 사용자의 원 요구는 "AI가 필요한 정보를 질문하고, 사용자가 자료 첨부 혹은 대답을 통해 꾸준히 완성"하는 흐름이다. 이 흐름은 start/add/next/review/simulate로 닫힌다. `answer`, `attach`, `import`를 별도 명령으로 분리하면 기능 수가 늘고 사용자가 선택 부담을 갖는다.
- **대안 검토**:
  - `persona answer`, `persona attach`, `persona import`: 내부 구현은 명확하지만 UX와 문서 표면이 커져 제외.
  - `me generate persona_*` recipe만 사용: 승인/거절 상태 전이와 raw privacy boundary를 recipe에 넣기 어렵고, Persona OS의 장기 상태 관리와 맞지 않아 제외.

## R-3 - Vault file surface: 네 파일로 시작

- **결정**: MVP는 `<vault>/90_System/AI/Persona/{Profile.md,Voice.md,Boundaries.md,Inbox.md}`만 생성한다.
- **근거**: `Coverage.md`, `DecisionRules.md`, `Evals/`는 유용하지만 첫 버전에서 사용자가 관리해야 할 표면을 늘린다. Coverage는 계산값으로 유지하고, decision style은 Profile 안 category로 시작한다.
- **대안 검토**:
  - `Coverage.md` 영속화: 디버깅에는 좋지만 stale 상태 관리가 필요해 MVP에서 제외.
  - `DecisionRules.md` 별도 파일: 장기적으로 좋지만 기존 `DecisionPatterns.md`와 중복 혼란이 있어 제외.
  - `Evals/ScenarioSet.md`: simulation 품질 측정에 좋지만 M5 이후 별도 feature로 다루는 편이 안전하다.

## R-4 - Persona module은 `profile/` 확장이 아닌 별도 vertical slice

- **결정**: 새 구현은 `src/synapse_memory/persona/`에 둔다.
- **근거**: 기존 `profile/`은 Claude Code history에서 `ProfileFact`/`DecisionPattern` 후보를 추출해 `MemoryInbox`로 보내는 역할이다. Persona OS는 사용자가 직접 제공한 답변/첨부, pending/accepted/rejected 상태, simulation boundary까지 포함하므로 독립 모듈이 테스트와 유지보수에 유리하다.
- **대안 검토**:
  - 기존 `profile/`에 모두 추가: 코드 reuse는 쉽지만 책임이 섞이고 legacy `Profile.md` compatibility 위험이 커져 제외.
  - `recipes/`로 구현: generation에는 좋지만 evidence lifecycle과 review state를 다루기 어려워 제외.

## R-5 - 첨부 지원 범위: text/markdown 우선, PDF는 명확히 거절

- **결정**: MVP는 직접 텍스트와 `.txt`, `.md`, `.markdown` 파일만 지원한다. `.pdf`는 "아직 지원하지 않음"을 명확히 출력하고 후속 feature로 분리한다.
- **근거**: 현재 package dependency는 `PyYAML`만 필수이며 PDF parser dependency가 없다. Persona OS의 핵심 리스크는 첨부 종류보다 raw boundary와 승인 flow이므로, 새 parser dependency를 먼저 넣는 것은 범위를 키운다.
- **대안 검토**:
  - PDF parser를 즉시 추가: user story에는 매력적이지만 dependency/test surface가 커져 MVP에서 제외.
  - 모든 파일을 plain text로 읽기: binary/PDF에서 깨진 텍스트와 privacy leak 위험이 있어 제외.

## R-6 - Claim extraction: deterministic scaffold + LLM boundary 분리

- **결정**: MVP 구현은 redacted evidence를 받아 `PersonaClaim` 후보를 만드는 extraction boundary를 두되, tests에서는 deterministic extractor를 주입한다. 실제 LLM extraction은 기존 `ai_api.complete_structured`와 redaction pipeline 위에 얇게 붙인다.
- **근거**: Constitution의 test-first 원칙상 LLM 결과에 의존한 테스트는 flaky하다. 동시에 PersonaClaim 품질은 LLM이 필요한 영역이므로 boundary를 분리해야 한다.
- **대안 검토**:
  - 전부 LLM extraction: 테스트 불안정성과 비용 때문에 제외.
  - 전부 규칙 기반 extraction: 빠르지만 사용자의 말투/선호/금지 영역을 충분히 추출하기 어려워 제외.

## R-7 - Simulation은 accepted claim만 사용

- **결정**: `persona simulate`는 `Profile.md`, `Voice.md`, `Boundaries.md`에 승인된 claim만 사용한다. `Inbox.md` pending/conflicted/rejected claim은 prompt에 포함하지 않는다.
- **근거**: Persona OS의 신뢰는 "사용자가 승인한 나"에 달려 있다. pending 후보가 답변에 섞이면 AI가 추출한 오해가 사용자의 persona로 작동한다.
- **대안 검토**:
  - pending claim도 낮은 weight로 사용: 답변 품질은 올라갈 수 있지만 승인 경계를 흐려 제외.
  - raw evidence를 simulation 때 다시 검색: privacy 경계와 latency가 커지고, 승인 기반 원칙과 맞지 않아 제외.

## R-8 - AGENTS context update 방식

- **결정**: 이 repo에는 별도 agent context update script가 없으므로, `AGENTS.md`의 SPECKIT marker를 `specs/010-persona-os/plan.md`로 직접 갱신한다.
- **근거**: `.specify/scripts/bash/`에는 setup/check script만 있고 update-agent-context script가 없다. 스킬의 결과 요구사항은 "agent context file update"이므로 marker를 직접 갱신하는 것이 현재 repo 구조에 맞다.
- **대안 검토**:
  - 없는 script를 새로 추가: Persona OS 계획 범위를 벗어나 제외.
  - AGENTS를 갱신하지 않음: 이후 구현 단계가 009 plan을 읽게 되어 잘못된 맥락으로 흐르므로 제외.
