# Changelog

All notable changes to Synapse Memory are documented here.

## [0.7.0] — 2026-05-13

### Added — Persona OS (M1) + 신뢰 가드 + Quick mode

- **`persona ingest --file <path>`** (M1b): 외부 markdown / txt 자료를 ProfileFact 후보로 흡수.
  vault `90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md` 에 PR 로 추가, 사용자가 직접 검토.
- **`persona design-project "<idea>"`** (M1c): Profile + ProjectCard RAG 기반 새 프로젝트 설계
  초안을 `20_Projects/Drafts/` 에 저장. 사용자 voice·tech·work_style 반영.
- **`voice` 카테고리**를 PROFILE_CATEGORIES 에 추가 — 말투·문장 길이·표현 선호.
- **`synapse-memory daily --quick`**: 첫 호출 30분~1시간 → **~3분** 목표.
  최근 7일 modified 노트 cutoff (mirror 89% 감소), classify cluster cap 10,
  update_profile auto-skip. full pipeline 은 별도 cron 또는 수동 `daily` 호출.
  ⚠ ChromaDB write 동시성 회피를 위해 `--quick` 과 full 동시 실행 금지.
- **`synapse-memory doctor --fix-config`**: config.yaml vault 경로와 vault detection
  결과 불일치 시 *경고만* 출력 (silent overwrite 차단). 명시 flag 후에만 적용.

### Changed

- `me` namespace → **`persona`** deep rename. CLI 표면뿐 아니라 모듈 / 함수 / `last_response`
  command 식별자 (`me.generate.*` → `persona.generate.*`) 모두 갱신. pre-product 단계라
  legacy migration 없음.
- README hero 를 **2 entry meta** (`/synapse-onboard` + `/synapse-assistant`) 로 축소.
  13개 slash 명령을 4-tier (entry meta / direct atom / maintenance / power) 로 분류.
- `persona.decide()` **신뢰 가드** 추가: RAG 매치 0개 또는 가장 가까운 distance > 0.6 →
  LLM 호출 차단 후 거부 응답. Profile 위장 인용으로 generic 답 만드는 위험 차단.
- `persona.decide()` Profile 로딩의 5000자 silent truncation 제거. 시스템 prompt 32KB
  cap 이 안전망 — 초과 시 `RecipePromptTooLargeError` 명시적 실패.
- 13개 slash 명령을 4-tier (entry meta / direct atom / maintenance / power)
  로 분류, README 가 entry meta 2개만 가르치게 단순화.
- Codex default 모델 gpt-5.4 → gpt-5.5.
- README 와 docs 구조 단순화: 짧은 README 1개 + `docs/` 안 사용자 중심 문서
  4개로 통합. 이전 docs/ 안 개발자 reference 문서 삭제.

### Infrastructure

- `.github/workflows/ci.yml`: persona rename 반영 (me.py / test_endpoints_me_extra.py
  경로 갱신).
- Test 회귀 가드: **817 tests pass** (이전 716 + 신규 ~100).

### Internal

- 설치 state manifest smoke 커버리지 확대 (`installer/`).
- Monthly cost cap guard + config reference doc.
- specs/007-me-recipes/ → specs/007-persona-recipes/ rename.

## [0.6.2] — 2026-05-12

- 비개발자용 GUI installer (specs/009-non-developer-onboarding).
- Doctor `--fix` whitelist repair (private permissions + runtime shim).
- Plugin marketplace 등록 (Claude Code + Codex).
