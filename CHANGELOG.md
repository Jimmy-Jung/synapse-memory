# Changelog

All notable changes to Synapse Memory are documented here.

## [0.8.5] — 2026-05-15

### Fixed — CLI 안내 텍스트의 PARA 폴더 하드코딩 (#12)

- `cli.py:cmd_profile_update` / `cmd_persona_ingest` 가 MemoryInbox PR 저장
  후 출력하던 "검토 후 vault 90_System/AI/Profile.md, DecisionPatterns.md
  반영" 안내가 정적 문자열이라, 사용자가 `vault_folders.system.ai.profile`
  /`.decision_patterns` 을 override 해도 잘못된 경로를 안내하던 문제 수정.
  이제 `get_config().vault_folders.system.ai.{profile,decision_patterns}`
  를 읽어 실제 설정 경로를 출력.
- 이슈 #12 (PARA 폴더 경로 외부화) 의 잔여 cosmetic 하드코딩 처리 — 핵심
  외부화 로직은 0.8.3 (dc3b1b7) 에서 이미 완료, 본 패치는 안내 메시지
  마무리.

## [0.8.4] — 2026-05-15

### Fixed — `daily` 파이프라인 비용·타임아웃 회귀

- `cli.py:daily` 가 `--classify-model` / `--generate-model` / `--profile-model`
  의 argparse `default` 값(`haiku`/`sonnet`/`sonnet`)을 그대로 사용해
  `~/.synapse/config.yaml` 의 `models.<provider>.<task>` 를 **완전히 무시**
  하던 버그 수정. 이제 CLI 인자가 명시되지 않으면 `_resolve_model()` 을 통해
  config 우선순위(`CLI 인자 → SYNAPSE_AI_PROVIDER → config.ai_provider`)를
  따른다. 영향: 사용자가 cost 절감을 위해 `card_generate: haiku` 로 바꿔도
  실제 daily 실행은 sonnet 으로 호출되어 의도한 절감이 일어나지 않던 문제.
- `cards/auto_generate.py:generate_company_card` 에 `timeout=DEFAULT_GENERATE_TIMEOUT`
  (180s) 누락. project 카드와 달리 회사 카드 호출만 `claude.py` 의
  `DEFAULT_TIMEOUT_SEC=60` 으로 떨어져 12KB 입력 처리 중 120s 부근에서
  반복 타임아웃이 발생하던 회귀 수정.

### Changed — `update_profile` 후속 단계 자동 보호

- `daily.py:DAILY_STAGES` 의 `update_profile` 의존성에 `generate` 추가.
- `_build_generate_action` 이 생성 0건 + 실패 ≥1건인 완전 실패 상황에서
  `RuntimeError` 를 발생시키도록 변경 → 단계 status 가 `FAILED` 가 되어
  `_blocking_dependency` 로직이 후속 `update_profile` 을 자동 skip.
  이전엔 generate 가 모두 실패해도 status=SUCCESS 였기에 update_profile 이
  16+ 회의 apfel redaction call 을 무의미하게 소비하던 비용 leak 차단.

### 결과

검증 실행 (`synapse-memory daily --quick`) 기준:
- 동일 `companies` 카드 생성: sonnet 80.2s / $0.17 → **haiku 32.4s / $0.10**
  (시간 60% ↓, 비용 42% ↓)
- daily 1회 총 시간: 102s → **55.8s** (46% ↓)
- 4회 연속 타임아웃 회귀(180s/120s/120s) 재발 없음

## [0.8.1] — 2026-05-13

### Added — Codex 플러그인 surface 보강

- Codex 플러그인 포맷은 `commands` 키를 인식하지 않으므로, 기존 `/sm:*`
  슬래시 명령들을 Codex 의 skill picker 에도 그대로 노출하기 위해 13 개
  의 개별 skill 폴더를 추가: `skills/{ask,recall,decide,doctor,fix,daily,
  resume,cost,feedback,assistant,cleanup,config,onboard}/SKILL.md`.
- 각 skill 의 `description` 은 "Use when the user ..." trigger 패턴으로
  작성해 router 가 의미가 비슷한 ask / recall / decide 사이에서 올바른
  skill 을 고를 수 있게 함. 본문은 실행할 `synapse-memory <subcommand>`
  명령과 인자 한 화면 요약.
- Claude Code 측 `commands/` slash surface 와 umbrella `skills/sm/`
  skill 은 그대로 유지 — 이번 릴리즈는 surface 추가만, 기존 동작
  변경 없음.

### Fixed — `/sm:assistant` 가 `config.yaml` vault 무시하던 문제 (#8)

- `assistant_status.resolve_vault_path()` 가 `SYNAPSE_OBSIDIAN_VAULT`
  환경변수만 읽어, env 미설정 시 `vault_path: null` → 카드 /
  MemoryInbox / cleanup 카운트가 모두 0 으로 떨어지던 버그 수정.
- 이제 fallback 체인: ① env var → ② `~/.synapse/config.yaml` 의
  `vault` 키 → ③ iCloud Obsidian 기본 경로
  (`~/Library/Mobile Documents/iCloud~md~obsidian/Documents`,
  실재 시). daily / config 파이프라인과 동일 소스를 참조해
  entrypoint 간 불일치 제거.
- 빈 vault 안내 메시지에 `synapse-memory config set vault ...` 도
  함께 노출.

## [0.8.0] — 2026-05-13

### Breaking — Slash 명령 prefix `synapse-memory` → `sm`

- Plugin 이름이 `synapse-memory` → **`sm`** 로 변경. 슬래시 명령 표시가
  `/synapse-memory:synapse-ask` → **`/sm:ask`** 로 짧아짐. command 파일명에서도
  `synapse-` prefix 제거 (`commands/synapse-ask.md` → `commands/ask.md`).
- Skill 폴더도 `skills/synapse-memory/` → `skills/sm/` 로 이동. Codex `plugins.*`
  config key, claude `plugin install` ref 모두 `sm@synapse-memory-marketplace`.
- 마이그레이션: 기존 사용자는 한 번 재설치 필요.
  ```bash
  claude plugin uninstall --scope user synapse-memory@synapse-memory-marketplace || true
  claude plugin marketplace remove --scope user synapse-memory-marketplace || true
  claude plugin marketplace add --scope user Jimmy-Jung/synapse-memory
  claude plugin install --scope user sm@synapse-memory-marketplace
  claude plugin enable --scope user sm@synapse-memory-marketplace
  ```
  Codex `~/.codex/config.toml` 의 `[plugins."synapse-memory@..."]` 블록을
  `[plugins."sm@..."]` 로 교체.
- CLI 바이너리(`synapse-memory`)와 marketplace 이름(`synapse-memory-marketplace`),
  GitHub repo 이름은 **그대로**. 이름이 바뀐 것은 slash prefix와 skill name뿐.

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
- README hero 를 **2 entry meta** (`/sm:onboard` + `/sm:assistant`) 로 축소.
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
