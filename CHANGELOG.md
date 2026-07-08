# Changelog

All notable changes to Synapse Memory are documented here.

## [2.0.1] — 2026-07-08

리뷰(종합 2/5)에서 지적된 무인운영 Ship Blocker + 검색·데이터 품질 gap을 코드 레벨로 해소한 패치 릴리즈.

### Fixed

- **무인운영**: 소스별 ingest 락(`ingest-{source}.lock`, PID-liveness stale 재획득) + small-doc dead-letter(연속 실패 격리)로 전역락 굶김·watermark 영구동결·silent loss 제거.
- **헤드라인 ask 일원화**: `ask`를 Card RAG(`endpoints.ask`) → 온톨로지 경로(`wiki.query.ask_wiki`)로 재배선. typed relation·concept·log가 답변에 도달.
- **relation 지표 방향맹**: coverage/orphan 계산에 inbound typed 엣지 반영 — inbound-only 허브(tuist·uikit·mcp) orphan 오집계 제거.
- **버전 정합 게이트**: 정체된 codex 매니페스트 정렬 + `test_version_consistency`로 pyproject 대비 drift CI 차단.
- **offset 영속화 O(N²)**: append-only JSONL 로그로 전환(checkpoint O(1)); rehydrate 스트리밍 write로 전체버퍼 복사 제거.
- **분류/회귀 가드**: concept.kind first-match → 스코어링(redux류 methodology 오분류 완화); CLI 디스패치 스모크(`ask` 이름충돌 seam).
- **문서 정리**: ask/recall 문서가 provider-only 반영(dense+BM25 RRF 문구 제거), specs/021 design의 삭제된 `about` relation 제거.

## [2.0.0] — 2026-07-07

구조 리디자인 (big-bang) + 온톨로지 완성. 설계: `specs/021-unified-model/design.md`,
검증: `specs/022-ontology-completion/review.md`.

### Added

- **온톨로지 완성 (S1–S7)**: competency-question 스위트(15개 중 14개 supported) +
  relation coverage 지표(`doctor`: typed_relation_coverage/legacy_related_residual/orphan_ratio).
- **Ingest Gatekeeper**: continuant(project/company/concept/profile)의 무타입 `related`
  차단·경고, lint coverage gate — typed 그래프 회귀 방지.
- **타입 인지 retrieval**: 관계 타입별 이웃(`typed_neighbors`), 역인덱스(`reverse_relations`),
  질의 의도 기반 역방향 확장, `part_of`/`broader` transitive 확장(depth≤2),
  `same_as` 대칭 확장, ask 컨텍스트의 관계 타입별 grouping.
- **시간 무효화**: `supersedes` 발행 시 대상 자동 무효화(`status=superseded` + `t_invalid`),
  기본 조회는 현재 유효만, recall은 supersedes 이력 확장.
- **분류**: `concept.kind` enum(technology/tool/algorithm/methodology) + 백필 태거(dry-run),
  decision은 occurrent(insight/log) 레인으로 유도. `broader`(SKOS) 관계 신설, `about` 삭제.
- 반복 log → insight 승격 후보(`wiki/promotion.py`), episodic 제외 검색 옵션(`exclude_types`).

### Fixed

- `synapse-memory ask` CLI가 `cli.ask` 서브모듈 이름 충돌로 크래시하던 버그.
- 기본 모델을 스폰되는 provider(config) 기준으로 해석 — Claude Code 세션 안에서
  codex 실행 시 sonnet이 전달되던 불일치 제거(runtime 감지는 `auto`일 때만).

### Changed

- **단일 엔티티 모델**: v1 Cards(Project/Company/Insight) + v2 WikiPage → 단일 타입 `Entity` + `schema.yaml`
  (types: project/company/concept/insight/log/profile; typed relations; created/observed_at/supersedes 시간성).
- **단일 인제스트 파이프라인**: v1 cluster→classify→generate 제거, per-doc LLM 통합(apply_ops)으로 수렴.
  daily = collect → ingest → lint.
- **공유 계층 SSOT**: vault-resolution(config), retrieval 패키지, llm 어댑터, page model/store 분리.
- `cli.py`(4030L) → `cli/` 패키지(command-noun별 모듈).

### Removed

- Obsidian-UI 표면(moc/·index_md·SCHEMA writer·Dataview doctor·node 태그·spec 015).
- 죽은 코드: `rag/`·`installer/`·`llm/credentials`·`feedback/apply`, 미사용 collector 5개(cursor/continue/aider/day_one/gmail).

### Notes

- 개발단계 big-bang: 하위호환·마이그레이션 없음. 기존 vault 페이지는 L0 raw 재인제스트로 재생성(`docs/reingest-runbook.md`).

## [1.20.0] — 2026-07-03

### Added

- `synapse-memory compact-raw`를 추가했다. 이미 ingest된 `claude-code`/`codex`
  raw mirror에서 provider 통합에 쓰지 않는 tool I/O 라인을 gzip sidecar로 분리해
  `~/.synapse/private/raw` 용량을 줄인다. 기본은 dry-run이며 실제 적용은
  `synapse-memory compact-raw --apply --yes`, 원복은
  `synapse-memory compact-raw --rehydrate --apply --yes`로 실행한다.

### Changed

- raw mirror offset 처리를 line-boundary 기준으로 보수화했다. compact나 rotation 뒤
  offset이 중간 라인을 가리키면 기존 offset을 신뢰하지 않아 잘린 JSONL 조각을
  ingest하지 않는다.
- 자동 collector 표면을 실제로 쓰는 8개 소스로 줄였다. 기본 자동 mirror는
  Claude Code, Codex, Cursor, Continue.dev, Aider, Obsidian, Day One이고,
  Gmail Sent만 opt-in으로 유지한다.

### Removed

- 개인정보·운영 잡음이 크거나 유지 가치가 낮은 collector를 제거했다:
  Apple Health, Apple Notes, Browser History, Calendar, `git_self`, iMessage,
  Screen Time, Shell History, VS Code Local History.

## [1.19.8] — 2026-07-01

### Changed

- `resume` 스킬을 얇은 CLI 한 방 합성에서 **4단계 네이티브 워크플로**(회사 심층조사 → 프로젝트 매칭 → 초안 → 최종)로 재작성했다.
- 실행 정책을 "필수(최고 모델·Ultracode)"에서 **best-effort**로 현실화했다. 모델·effort·병렬성은 호출 환경 설정이며 스킬은 단계 게이트(초안 검토·팩트체크)만 보장한다.

### Added

- `skills/resume/references/` 5종을 추가해 이력서 양식을 통일했다: `resume-template`, `style-guide`, `company-analysis-template`, `draft-template`, `interview-guide`.
- cold-start 인터뷰 분기(첫 사용·기존 이력서/자소서 없음), no-JD 모드, 복수 포지션 확정, idempotency 규칙(`status: draft|approved` 재생성 방지).
- 이력서 소스 자료를 `Entities/Projects` 외 `Profile`/`Concepts`/`Insights` 전체로 확장했다.
- **Phase 4 정직성 게이트**: 초안 "제출 전 팩트체크"의 미해결(증빙 준비·표현 주의) 항목이 최종본에 유출되지 않도록 강제한다.

### Fixed

- 이력서 템플릿의 경로형 wikilink(`[[Entities/Projects/...]]`)를 vault가 유일 해석하는 bare `[[name]]` 형식으로 통일했다.

## [1.19.7] — 2026-06-28

### Changed

- wiki `log.md`(ingest/lint changelog)를 iCloud-synced vault 루트에서 vault 밖
  `~/.synapse/private/`(0700, iCloud sync 제외)로 이전했다. 매 ingest마다 1줄씩
  무한 append되어 Obsidian 파일목록·그래프와 iCloud 동기화에 잡음을 쌓던 문제를
  없앤다. 이 로그는 코드가 다시 읽지 않는 write-only audit trail이라 위치만 옮겨도
  안전하며, cost/feedback 로그와 같은 L0 디렉터리에 모인다. 줄 형식(`- <iso> <msg>`)과
  redaction은 그대로다. `log_path()`/`append_log()`의 `vault_path` 인자는 제거됐다.
  기존 vault의 `log.md`는 새 위치로 1회 이전하면 된다(이력 보존).

## [1.19.6] — 2026-06-26

### Fixed

- wiki ingest가 노트의 날짜(`title`/`slug`/파일명/`updated`)에 원본 기록일이 아니라
  **처리일(today)**을 박던 버그를 고쳤다. codex 세션을 며칠 뒤 배치 처리하면, 화면
  녹화 activity-log류는 본문이 상대 타임스탬프(`00:00:00~`)만 담아 LLM이 제목/slug
  날짜를 자기 오늘로 채우고 `apply_ops`도 today로 stamp해, 양쪽이 처리일로 수렴했다
  (예: 06-16 세션이 06-26로 기록). 이제 `rawdoc.source_date_from_ref()`가 codex ref
  경로(`sessions/YYYY/MM/DD/`)에서 기록일을 뽑아 통합 프롬프트와 `apply_ops` 양쪽에
  주입한다. 날짜가 없는 source(claude-code)는 기존대로 today로 폴백한다.

## [1.19.5] — 2026-06-22

### Fixed

- launchd watch 데몬이 `engine=codex`에서 모든 문서를 `AIUnavailableError`(Codex
  CLI 미설치)로 실패시키던 버그를 고쳤다. `_daemon_path`가 `claude`만 실제 위치를
  해석해 PATH에 넣고 `codex`는 누락했기에, codex가 nvm/brew 등 비표준 경로에 설치된
  환경에서 데몬이 CLI를 찾지 못했다. 결과적으로 매시간 사이클이 돌아도 wiki 페이지가
  하나도 생성되지 않았다(`pages=0`). 이제 claude/codex 모두 설치 시점에 위치를 해석해
  데몬 PATH에 추가한다. 설정 변경 적용에는 `synapse-memory watch install` 재실행이
  필요하다.

## [1.19.4] — 2026-06-22

wiki 자동 유지엔진의 토큰 소모를 줄였다. watch 데몬이 진행 중인 세션 jsonl을
매 사이클 전문(全文) 재전송하던 것이 주원인이었다(유휴 사이클은 이미 LLM 0회라
실행 주기 자체는 약한 레버).

### Changed

- `maintenance.idle_minutes` 기본값 3→30 (대화 종료 후 1회만 ingest),
  `max_docs_per_cycle` 25→10 (사이클당 LLM 호출 천장),
  `interval_minutes` 20→60 (wakeup 빈도 72→24회/일).
- `ingest_source`의 `semantic_retrieval` 기본값을 끄로 변경해 small 문서의
  provider 관련-페이지 선별 호출을 제거했다(문서당 LLM 2→1회).

### Added

- offset ingest: 세션 jsonl에서 이미 처리한 byte offset(`ingest_state.json`의
  `__offsets__`)을 기록하고, 다음 사이클은 그 이후 tail만 전송한다. 자라는
  단일 세션의 전문 재청구를 차단한다. 파일 로테이션/축소 시에는 전문 재처리해
  데이터 유실을 막는다.

## [1.19.3] — 2026-06-22

### Changed

- `synapse-memory setup`의 기본 동작을 repo 파일 수정 없는 hook 등록으로
  변경했다. `AGENTS.md`/`CLAUDE.md` marker 삽입은 이제 `--target`을 명시한
  경우에만 수행한다.
- `--no-marker` 옵션을 제거하고, doctor/hook 안내와 README, slash command,
  skill 문서를 새 기본값에 맞춰 정리했다.

## [1.19.2] — 2026-06-22

코드베이스 감사 결과 중 안전한 중복 제거만 적용했다. 동작 변화 없음.

### Changed

- 9개 collector `mirror.py`가 각자 복제하던 파일 상태 헬퍼(`FileState`,
  `file_sha256`, `load_states`, `save_states_atomic`)를 공용
  `collectors/_filestate.py`로 통합했다. `_sqlite_mirror`는 하위 호환을 위해
  re-export한다.
- claude/codex 어댑터가 중복 보유하던 JSON 파싱 헬퍼(`strip_code_fence`,
  `extract_first_json_value`, `parse_json_with_fallback`)를 공용 `llm/_json.py`로
  통합하고, provider별 차이는 인자로 분리했다.
- ruff `combine-as-imports`를 활성화해 alias·중복 import 블록을 단일 statement로
  정리했다.

## [1.19.1] — 2026-06-21

watch/ingest 기본 실행 provider를 Codex로 전환하고, 런타임 자동감지보다
사용자 config가 우선되도록 정렬했다.

### Changed

- 기본 `ai_provider`와 `maintenance.engine`을 `codex`로 변경했다.
- provider 미지정 AI 호출이 `~/.synapse/config.yaml`의 `ai_provider`를 먼저
  따르도록 해 Codex/Claude 실행 환경 변수에 따라 watch/ingest provider가
  흔들리지 않게 했다.
- `ingest_source()` 통합 호출이 config provider를 명시 전달하도록 보강했다.
- README installer 링크와 Claude/Codex plugin manifest, marketplace version을
  `1.19.1`로 정렬했다.

### Documentation

- 비용 문서의 Claude 전용 표현을 설정된 provider 기준 설명으로 수정했다.

## [1.19.0] — 2026-06-21

Codex/Claude 플러그인에서 가장 기본적인 hook과 skill 진입점이 실제 CLI 계약과
일치하는지 재검토하고, 자동 점검이 가능한 read-only 표면을 보강했다.

### Fixed

- SessionStart hook 설치/진단 경로를 절대 경로 기반으로 정렬해 Codex 설정에서
  legacy hook 명령이 남아도 `doctor`가 ready 여부를 정확히 판단하도록 했다.
- `$recall`, `$resume`, `$decide`, `$assistant`, `$config`, `$cleanup`,
  `$onboard` skill 문서가 존재하지 않는 예전 top-level CLI를 안내하던 문제를
  실제 `persona`, `assistant-status`, `config <subcommand>`, `cleanup <action>`
  명령으로 수정했다.
- Codex wrapper skill(`plugins/sm/skills`)을 root skill과 다시 동기화해
  marketplace 설치 경로와 source checkout 경로의 동작 차이를 없앴다.

### Changed

- `synapse-memory ingest-audit --json`, `synapse-memory card list --json`,
  `synapse-memory cleanup scan --dry-run`, `synapse-memory cleanup apply --dry-run`
  을 지원해 플러그인/자동화가 read-only 점검 결과를 구조적으로 읽을 수 있게 했다.
- 패키지 버전, Claude/Codex manifest, Codex marketplace, README installer 링크를
  `1.19.0`으로 정렬했다.

## [1.18.1] — 2026-06-20

Codex plugin marketplace가 1.18.0 이후 추가된 install source 보정까지
공식 release/tag/installer에 포함되도록 patch release를 발행한다.

### Fixed

- Codex CLI가 root source marketplace 항목을 `codex plugin list`와
  `codex plugin add` 표면에 노출하지 못하던 문제를 수정했다.
- Codex용 `plugins/sm` wrapper source를 추가해 marketplace catalog,
  install cache, `skills/` 로딩 경로가 같은 구조를 사용하도록 정렬했다.

### Documentation

- Codex plugin 검증 명령을 현재 CLI 출력 기준에 맞춰 갱신했다.

## [1.18.0] — 2026-06-20

Codex 세션을 wiki ingest의 정식 소스로 추가하고, 대형 Codex 문서가
backfill 비용과 시간을 무한히 소모하지 않도록 ingest 경로를 보강했다.

### Added

- `collect codex`, `ingest --source codex`, `backfill --source codex`,
  `watch run`의 Codex source 통합을 추가했다.
- `synapse-memory ingest-audit`을 추가해 backfill 전 pending 문서 수,
  대형 문서 분류, 예상 LLM 호출 수를 로컬에서 확인할 수 있게 했다.
- `ingest`, `backfill`, `ingest-audit`에 `--no-semantic-retrieval` 옵션을
  추가해 대량 backfill canary에서 작은 문서의 관련 페이지 선별 호출을
  생략할 수 있게 했다.

### Changed

- 40,000자 초과 문서는 전체 본문을 한 번에 보내지 않고 비용 예산에 맞춰
  샘플링하며, 120,000자 초과 문서는 LLM 호출 없이 격리하고 watermark를
  전진시켜 backlog jam을 방지한다.
- wiki ingest 구조화 호출 timeout을 300초로 늘려 중간 크기 문서의 정상
  처리를 더 안정적으로 만들었다.

### Fixed

- 동일 mtime 파일 정렬 충돌로 raw 문서가 누락될 수 있던 증분 collect
  데이터 손실을 수정했다.
- 대형 문서 처리 실패가 watermark를 전진시키지 못해 같은 문서를 계속
  재시도하며 비용을 반복 소모하던 문제를 수정했다.
- wiki page update 시 기존 `related`와 `sources` metadata가 덮어써져
  provenance가 사라질 수 있던 문제를 수정했다.

## [1.17.5] — 2026-06-19

watch LaunchAgent가 정상 실행 중이어도 launchd 환경에서 `claude` CLI를 찾지 못해
wiki 갱신이 `docs>0, pages=0`으로 조용히 멈추던 문제를 수정했다.

### Fixed

- `synapse-memory watch install`이 생성하는 LaunchAgent plist에 데몬용
  `EnvironmentVariables.PATH`를 추가해 launchd 기본 PATH 밖에 있는 `claude`와
  `synapse-memory` 실행 파일을 찾을 수 있게 했다.
- 데몬 PATH 생성 시 `.codex/tmp`, `.venv`, `/tmp` 같은 임시 경로를 영구 저장하지
  않고, resolved 바이너리 디렉터리와 사용자/system bin 후보만 포함하도록 제한했다.
- Claude provider가 `PATH` 조회에 실패해도 `~/.local/bin/claude`,
  `/usr/local/bin/claude`, `/opt/homebrew/bin/claude` 실행 파일을 fallback으로
  검사하도록 했다.
- `watch run`이 ingest error 수를 stdout에 표시하고 각 error를 stderr에 기록하며,
  error가 있으면 non-zero exit code를 반환하도록 해 launchd 로그에서 실패 원인을
  바로 볼 수 있게 했다.

### Documentation

- `WATCH_DAEMON_DIAGNOSIS.md`에 원인 사슬, 적용된 수정, 기존 LaunchAgent 재설치
  필요성, backlog drain 절차를 정리했다.

## [1.17.4] — 2026-06-17

local embedding/BM25/vector index hot path를 제거하고, Claude/Codex provider retrieval과 markdown-backed index로 wiki·recipe·persona 질의를 단순화했다.

### Added

- `CardIndex`와 `page_index`를 추가해 Project/Company Card 및 wiki page metadata를 markdown 파일에서 직접 조회.
- 020 provider-only retrieval 설계 문서와 migration stage 기록을 추가.

### Changed

- `ask`, `persona`, recipe pipeline, wiki query가 로컬 vector store 대신 provider가 vault/page context를 직접 읽는 흐름을 사용.
- daily/watch/launchd 경로에서 삭제된 local ML index 유지보수 작업을 제거.
- 테스트 suite를 provider-only retrieval 계약에 맞게 재정렬.

### Removed

- `sentence-transformers`, `numpy`, `rank-bm25` 기반 BM25/embedding/hybrid/vector index 모듈과 관련 CLI/tests 제거.

## [1.17.3] — 2026-06-16

wiki ingest의 librarian 호출이 Claude/Codex provider 모두에서 구조화 JSON을 안정적으로 받도록 정리했다.

### Fixed

- Claude provider가 `complete_structured` 호출에서 `structured_output=True`를 우선 적용하고, 명시적 verbose override를 받을 수 있게 해 JSON-only 응답 계약을 안정화.
- Codex provider가 구조화 출력 요청에서 `codex exec --json` 이벤트 스트림을 해석해 최종 assistant 텍스트만 반환하도록 수정.
- wiki ingest 통합 prompt가 vault의 `SCHEMA.md` 경로를 함께 전달해 사서가 현재 wiki 구조 규칙을 참조할 수 있게 보강.

## [1.17.2] — 2026-06-15

사용자가 SessionStart hook(예: caveman plugin)을 켠 상태에서 ingest/watch/backfill이 전부 깨지던 문제를 수정했다.

### Fixed

- ingest 내부 `claude --print` subprocess(사서)가 사용자 settings를 상속해 SessionStart hook의 주입 컨텍스트를 받으면, 사서가 JSON 대신 압축 텍스트로 응답해 파싱이 실패하고 0 페이지로 끝나거나 재시도가 반복돼 hang하던 버그 수정. `_build_cmd`에 `--setting-sources ""`(user/project/local settings 미로드 → hook·plugin 주입 차단)를 추가해 격리. `--bare`와 달리 OAuth/keychain 인증은 그대로 유지된다.

### Changed

- 사서 subprocess에 `--strict-mcp-config`(MCP 서버 미로드)와 `--exclude-dynamic-system-prompt-sections`(동적 시스템 프롬프트 섹션 제거)를 추가해 불필요한 컨텍스트와 cache 생성을 절감.

## [1.17.1] — 2026-06-15

1.17.0에서 apfel/redaction 제거 후 남은 레거시 잔재를 정리하고, 그 과정에서 raw 색인 버그를 수정했다.

### Fixed

- `rag index --include-raw`가 더 이상 존재하지 않는 `<L0>/redacted/claude-code`를 읽어 Claude Code raw chunk를 조용히 0개로 누락하던 버그 수정 — collector가 mirror하는 `<L0>/raw/claude-code`를 읽도록 정정.
- doctor 진단에서 제거된 apfel/L0-private 항목을 빼고 v2 wiki 파이프라인(페이지·watch 데몬·maintenance engine) 점검을 추가.

### Removed

- 고아 문서/스킬 삭제: `docs/local-llm.md`, `skills/redact/`(`/sm:redact`), `commands/redact.md`.
- `CostProvider` enum과 pricing 분기에서 `apfel` 제거.

### Changed

- 죽은 redaction 스캐폴딩 제거: `raw_chunks_from_file`의 항등 `redact` 콜백, `IngestResult`/`IngestedFile`의 `*_redacted` 필드명을 raw passthrough 현실에 맞게 정리.
- redaction/apfel을 전제하던 stale 주석·문서·스킬·매니페스트 텍스트를 v2 raw-passthrough 기준으로 갱신.

## [1.17.0] — 2026-06-15

Karpathy의 "LLM-maintained wiki" 패턴을 따르는 v2 엔진을 도입했다. 어떤 AI 툴(Claude/Codex 등)에서 대화하든 그 기록을 자동으로 인식해, 사람이 매일 수동 갱신하지 않아도 Obsidian vault에 상호 링크된 wiki를 구축·유지한다. 설계는 `specs/019-llm-wiki-redesign/`에 있다.

### Added — Wiki Foundation (P0)

- `synapse_memory.wiki.page`: 6개 타입(project/company/person/concept/profile/insight)을 단일 frozen `WikiPage`로 표현하는 통합 페이지 모델 — frontmatter serialize/parse, 디스크 I/O(`save_page`/`load_page`/`list_pages`), slugify, 위키링크 헬퍼(`extract_wikilinks`/`with_related`).
- vault 루트 `SCHEMA.md` 생성기 — 어떤 에이전트든 읽고 wiki 유지법(ingest/query/lint 규약)을 알 수 있는 "wiki의 CLAUDE.md".
- config: `maintenance`(유지엔진 `claude`/`codex`, `idle_minutes`)와 `vault_folders.wiki`(Entities/Concepts/Profile/Insights) 설정.

### Added — Ingest Engine (P1)

- `synapse-memory ingest --now`: claude-code 대화 raw → 관련 기존 페이지 선별(이름매칭 + 링크 1-hop) → `complete_structured`로 통합(integrate-not-index) → `save_page` 적용 + 양방향 링크 + `log.md` 기록.
- 소스별 watermark로 증분 처리, per-doc 체크포인트로 중단-재개 지원.

### Added — Wiki-first Search + Write-back (P2)

- wiki 페이지를 RAG에 인덱싱하고, 관련페이지 선별에 의미유사도 top-k를 결합(이름+의미+링크 하이브리드).
- `synapse-memory wiki ask`: wiki 페이지 근거로 답하고 각 주장에 `[[페이지]]` 인용, 가치 있는 답은 Insight 페이지로 환원(write-back) → 다음 질문에 재사용. `synapse-memory wiki reindex`.

### Added — Automated Watch Daemon (P3)

- `synapse-memory watch run|install|uninstall|status`: launchd `WatchPaths`(네이티브 FSEvents)가 raw 변화 시 깨우면, 단일 동시성 락 아래 유휴(settled) 파일만 자동 ingest. 진행 중 대화의 부분 로그는 건너뛴다.

### Added — Lint (P4)

- `synapse-memory lint --now`: 구조 결함(끊긴 역링크·죽은 링크·고아)은 자동 수정하고, 진위 판단이 필요한 것(낡음 의심·병합 후보)은 `index.md` 검토 큐에 쌓는다("구조는 자동, 진실은 사람"). 마커 기반이라 사용자 편집 보존.

### Added — Backfill (P5)

- `synapse-memory backfill`: 빈 vault에서 전체 대화 이력을 재개 가능한 배치로 한 번에 구축. 전부 실패하는 배치를 감지해 무한루프를 방지한다.

### Removed — Local LLM + Redaction (apfel)

- Apple FoundationModels(apfel) 로컬 게이트와 2-pass redaction 서브시스템을 완전히 제거했다(v2는 raw를 클라우드 CLI에 직접 전달하는 것을 신뢰 전제로 한다).
- `redact`/`redactlist`/`redact-file` CLI 명령, redaction config 키, PII golden eval을 제거했다. `estimate_tokens`는 `llm/tokens.py`로 이전했다.

## [1.16.2] — 2026-06-12

### Added — Codex Hook Support

- `synapse-memory hook install`이 Claude Code `~/.claude/settings.json`뿐 아니라
  Codex `~/.codex/hooks.json`에도 `SessionStart` command hook을 설치한다.
- Codex hook은 `startup|resume` matcher와 `Loading Synapse Memory context`
  status message를 사용해 기존 hook runner의 Profile/DecisionPatterns 주입을
  Codex 세션 시작에도 적용한다.

### Changed — Hook Diagnostics

- `synapse-memory doctor`와 `hook install|uninstall` 출력이 Claude Code/Codex
  공통 SessionStart hook 상태를 설명하도록 갱신됐다.
- README의 “Codex hook 미지원” 안내를 제거하고, Codex의 `/hooks` 신뢰 승인
  필요성을 명시했다.

### Fixed — Hook Lifecycle Safety

- Codex hook 설치, 중복 설치 방지, 진단, 제거 테스트를 추가했다.
- `hook uninstall`은 Claude Code와 Codex 양쪽에서 Synapse hook entry만 제거하고
  사용자의 다른 hook은 보존한다.

## [1.16.1] — 2026-06-11

### Added — Hook Context Injection

- `synapse-memory hook install|uninstall|run`을 추가했다. Claude Code
  `SessionStart` hook이 등록 프로젝트에서 세션 시작 시 사전 렌더된
  Profile/DecisionPatterns 요약을 주입한다.
- `synapse-memory context render`를 추가했다. `AGENTS.md`/`CLAUDE.md` marker를
  다시 쓰지 않고 hook context cache만 갱신할 수 있다.
- `synapse-memory setup --no-marker`를 추가했다. repo 파일 수정 없이 프로젝트를
  registry에 등록하고 hook 전용 context cache를 생성한다.
- `synapse-memory setup --target codex` alias를 추가했다. Codex용 `AGENTS.md`
  marker만 갱신한다.
- `hook.suggest_register` config를 추가했다. 켜면 미등록 git repo에서 세션당 1회
  `setup --no-marker` 등록 힌트를 출력한다.

### Changed — Context Freshness

- `setup`, `sync`, `context render`, `hook install`이 `~/.synapse/context/` 아래
  `rendered.md`와 hook runtime `settings.json` sidecar를 갱신한다.
- `/sm:apply-profile` 승인 반영 후 `synapse-memory context render`를 실행하도록
  skill/command 문서를 갱신했다. Profile 변경 직후 hook context staleness를 줄인다.
- `synapse-memory doctor`가 Claude Code SessionStart hook 설치 상태를 점검하고
  미설치 시 `synapse-memory hook install`을 안내한다.

### Fixed — Hook Runtime Safety

- hook runner는 stdlib-only fast path로 실행되며, 모든 예외를 침묵 처리해 세션
  시작을 막지 않는다.
- Claude settings.json 기록을 임시 파일 + `os.replace` 원자적 쓰기로 변경했다.
- `cli.py`의 파일 전체 `E402` noqa를 import별 noqa로 좁히고, 기존 mypy 지적
  4건을 함께 정리했다.

## [1.16.0] — 2026-06-11

### Added — Knowledge Compounding P1

- `synapse-memory ask --save` 가 답변을 `InsightCard`로 저장한다. 저장 위치는
  `<vault>/20_Reference/Insights/<yyyy>/<mm>/`이며, 저장된 Insight는 다음
  RAG 인덱싱과 검색 대상이 된다.
- `rag index --rebuild` 가 Project/Company Card뿐 아니라 기존 InsightCard도
  재인덱싱하고 BM25 sidecar에 포함한다.

### Fixed — Insight 저장 안전성

- Insight 저장 시 질문과 답변을 모두 redaction 후 vault-visible markdown,
  filename slug, index display name에 사용한다.
- 같은 질문을 여러 번 저장해도 기존 Insight를 덮어쓰지 않고 `-2`, `-3`
  suffix를 붙여 별도 파일로 보존한다.

## [1.15.9] — 2026-05-29

### Fixed — Codex runtime daily/ask 안정화

- **Codex adapter** — `synapse-memory ask` 와 daily 내부 classify/generate가
  Obsidian vault 또는 임시 디렉터리처럼 git repo가 아닌 위치에서도 동작하도록
  nested `codex exec` 호출에 `--skip-git-repo-check` 를 추가했다. (#35, #36)
- **daily model resolution** — `SYNAPSE_AI_PROVIDER` 명시값 다음으로 실제
  Codex/Claude 런타임 환경을 감지해 task별 model을 선택한다. Codex 세션에서
  config 기본 provider가 Claude여도 `models.codex.classify` 를 사용해
  Claude 전용 `haiku` 모델로 떨어지는 실패를 방지한다. (#36)
- **RAG indexing** — Project/Company Card의 `domains`, `stack`, `keywords`,
  position keywords에 숫자처럼 사람이 편집한 비문자 YAML 값이 들어와도 문자열로
  정규화한 뒤 검색 텍스트를 생성한다. (#36)

## [0.15.8] — 2026-05-24

### Fixed — CLI 인식 실패 & `/sm:recall` 인자 파싱 오류

- **`bootstrap_runtime.sh`** — 설치 후 플러그인 훅이 bare `synapse-memory`
  호출 시 `command not found`로 실패하던 문제를 수정. 기존
  `~/.synapse/bin/synapse-memory` shim은 그대로 유지하면서, XDG user-local
  표준인 `~/.local/bin/`에 추가 symlink를 생성한다. 이 디렉터리는 uv·pipx·
  Claude Code CLI(`claude`) 모두 기본 설치 경로로 사용하므로 일반적인 macOS
  사용자 PATH에 이미 잡혀있다. 사용자 `~/.zshrc` / `~/.bash_profile`을
  건드리지 않는다.
  - `SYNAPSE_SKIP_LOCAL_BIN=1` 환경 변수로 opt-out 가능.
  - `SYNAPSE_LOCAL_BIN_DIR` 으로 대체 경로 지정 가능.
  - `~/.local/bin/synapse-memory`에 기존 비-symlink 정규 파일이 있으면
    덮어쓰지 않고 경고 후 skip (사용자 수동 설치 보호).
- **`commands/recall.md`** — `/sm:recall <주제>` 호출 시 `$ARGUMENTS` quote
  누락으로 셸이 공백 단위로 split 하여 CLI가 `unrecognized arguments`로
  거부하던 버그를 수정. `synapse-memory persona what-did-i-think
  "$ARGUMENTS"` 로 따옴표 추가. (`ask` / `decide` / `resume`은 이미 quoted
  상태였음 — `recall`만 누락.)

## [0.15.7] — 2026-05-23

### Fixed — Codex sessions 신호 누락

- Codex 0.131+ 부터 `~/.codex/history.jsonl` 기록이 사실상 멈추고 실제 사용
  신호가 `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` 에만 남는 환경
  변화로, `profile/extract.py` 의 ProfileFact / DecisionPattern 추출이
  `history.jsonl` 만 읽고 sessions 데이터를 통째로 무시하던 결함을 수정.
- `profile.extract._read_codex_sessions_tail` 신규 — 최신 rollout 파일에서
  `response_item.payload.{type=='message', role=='user'}` 라인만 추출.
  AGENTS.md / CLAUDE.md / `<system-reminder>` 등 자동 첨부 prefix 는 노이즈로
  스킵. token 비용 보호 위해 파일 수·메시지 수 cap.
- `extract_profile_facts` / `extract_decision_patterns` 모두 sessions tail 을
  history.jsonl 과 병행 source 로 사용. history.jsonl 이 stale 인 환경에서도
  자동 보충.

### Added — Codex rollout cwd 로 cluster 시드

- `clusters/identify.py` 가 `~/.synapse/private/raw/codex/sessions/` 의 첫
  `session_meta.payload.cwd` 로 ProjectCluster 시드. Claude Code 매칭이
  안 되던 GitLab / 사내 프로젝트도 cluster 후보로 인식.
- 동일 `Path(cwd).name` 일 때 Claude Code / Codex 시드가 자연스럽게 머지,
  `seed_kind` 가 `merged` 로 표시. `ProjectCluster.codex_jsonl` 필드 추가.
- `cards/auto_classify.classify_cluster` 가 cluster.codex_jsonl 에서 최신
  rollout 2개·각 6개 user message 까지 발췌해 분류 sample 끝에 첨부. vault
  노트만으로 `domain`/`skip` 으로 오분류되던 codex-only 프로젝트의 분류
  정확도 보강.

### Fixed — Codex 0.122.0 호환 + vault config 자동 작성

- 인스톨러의 `verify_codex_plugin` 단계가 Codex 0.122.0 에서 항상 실패하던
  회귀를 수정. 기존 검증은 `codex debug prompt-input` 출력에서 literal `sm:sm`
  토큰만 찾았는데, Codex 0.122.0 은 plugin skill 을 `<plugin>:<skill>` prefix
  로 노출하지 않고 `<plugins_instructions>` 섹션에 plugin displayName 만
  표시한다. 다중 signal (`sm:sm` / `sm@synapse-memory-marketplace` /
  `Synapse Memory`) 중 하나만 매칭돼도 통과하도록 패턴을 확장.
- verify 단계의 결과를 `failed`(`return 1`) 에서 `warning`(`return 0`) 으로
  강등. plugin cache 와 `config.toml` 활성화가 이미 성공한 시점이므로 surface
  가시성 검사는 보조 진단일 뿐이며, false negative 가 전체 install 을
  중단시키지 않도록 함. 이전에는 `set -euo pipefail` 때문에 verify 실패 →
  `activate_codex_plugin` `return 1` → `activate_plugins` 비정상 종료 →
  vault 설정 단계까지 도달하지 못했다.
- vault 선택 직후 `~/.synapse/bin/synapse-memory config set vault <path>` 를
  자동 호출해 runtime config.yaml 에 vault 경로를 기록. 이전에는 `.obsidian`
  디렉터리만 생성하고 끝나서 직후 `synapse-memory doctor` 가
  "config.yaml vault 미설정" 경고와 Private/Dataview 진단 None 오류를 띄웠다.
  runtime binary 가 없는 환경(설치 직후 미부트스트랩)에서는 `skipped` 로 기록.

## [0.15.6] — 2026-05-19

### Fixed — Codex daily 기본 실행과 최신 모델 정렬

- Codex `sm:daily` skill 과 Claude `commands/daily.md` 의 안내를 full pipeline
  기본으로 정렬. `--quick` 은 사용자가 빠른 실행/최근 변경분만 처리를 명시한
  경우에만 사용하도록 문구를 수정.
- Codex provider fallback 기본 모델을 `gpt-5.5` 로 갱신. config 가 비어 있거나
  provider 기본값으로 떨어지는 경로에서도 이전 `gpt-5.4` 로 실행되지 않도록
  정리.

## [0.15.5] — 2026-05-19

### Fixed — 릴리즈 버전 surface 정렬

- `v0.15.4` 배포에서 `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
  `uv.lock` 이 이전 버전으로 남던 release drift 를 정정.
- `release-check` / `release-publish` workflow 가 pyproject, `__version__`,
  plugin manifest, `uv.lock` package version 불일치를 모두 실패 처리하도록
  보강.
- `scripts/release.sh` 가 release branch 생성 시 `uv.lock` 도 함께 갱신하고,
  PR checklist 에 plugin manifest / lock 정합성 검증 항목을 반영.

## [0.15.4] — 2026-05-19

### Fixed — Profile ledger fingerprint dispersion

- `profile/ledger.py` 에 신규 `find_entry` 헬퍼 — 정확 fingerprint 매치 + 토큰
  Jaccard ≥ 0.75 fallback. `record_extraction` / `promote_candidates` /
  `mark_promoted` / `extract.save_profile_update._lookup` 모두 동일 매칭 정책으로
  통일.
- LLM 이 같은 관점을 매일 미세하게 다른 표현으로 추출해 ledger fingerprint 가
  매번 달라져 `seen_count` 가 영영 1 에 머물던 dispersion 문제를 해결. 흡수된
  entry 는 `statements` 에 표현 변종을 누적해 보관하며 `promote_candidates` 가
  사용하는 누적 신호도 정상 작동.
- `dedupe.py` 의 vault dedupe 와 동일한 0.75 임계치 — 정책 일치.

### Changed — `fast_path_confidence` 기본값 0.95 → 0.90

- `ProfileConfig.fast_path_confidence` 기본값 완화. 실측상 LLM peak confidence
  가 대부분 0.80~0.92 구간이라 0.95 는 너무 빠듯해 의미 있는 신호도 fast path
  를 못 타고 `awaiting` 만 누적되던 문제 해소.
- `dedupe` / `dismissed` 안전망이 vault 진입 전 다시 거르므로 noise 위험은
  제한적.

### Added — `profile-review-awaiting` CLI

- 신규 `synapse-memory profile-review-awaiting [--min-confidence X] [--dry-run]`
  명령. ledger awaiting 중 `peak ≥ X` & window 내 entry 를 `ProfileFact` /
  `DecisionPattern` 으로 변환해 MemoryInbox 후보 파일을 생성한다.
- `daily` 가 "신규 fact/pattern 0건" 으로 끝났지만 ledger 에 awaiting 후보가
  쌓여있을 때, 사용자가 임계치를 명시 완화해 검토할 수 있는 보조 경로.
- vault dedupe / dismissed 안전망이 그대로 적용 — 중복 후보는 자동 제외.
- 단위 테스트 용이성 위해 핵심 로직은 `ledger.collect_review_candidates` 로
  분리.

### Changed — `/sm:daily` 스킬 인터랙션 추가

- `commands/daily.md` 에 "낮은 신뢰도 후보 검토 제안" 섹션 추가. `update_profile`
  이 신규 0건이지만 ledger awaiting 합계가 > 0 일 때, AskUserQuestion 으로
  **0.85 / 0.80 / 스킵** 임계치 선택을 사용자에게 제공하는 흐름을 명시.
- 선택 시 `profile-review-awaiting --dry-run` → 본 실행 → `/sm:apply-profile`
  체인으로 이어진다. Constitution VI Installation Consent 준수 — 사용자 명시
  선택 없이는 자동 진입 금지.

## [0.15.3] — 2026-05-18

### Fixed — doctor `expanduser` 회귀

- `diagnose_private_folder_deny` / `diagnose_dataview_plugin` 가 `Config.vault`
  (`str | None`) 를 그대로 받아 `'str' object has no attribute 'expanduser'`
  로 실패하던 회귀를 수정한다. 두 함수 모두 입력 시그니처를 `Path | str` 로
  넓히고 내부에서 `Path(vault).expanduser()` 로 강제 변환한다.
- 영향: `synapse-memory doctor` 의 "Private 폴더 deny 진단" / "Dataview 플러그인
  진단" 두 단계가 ⚠ 로 실패하지 않고 정상 ✓/⚠ 결과를 반환한다. 기존 테스트
  (`test_doctor_private_check.py`, `test_doctor_dataview_check.py`) 는 `tmp_path`
  를 사용해 영향 없음.

## [0.15.2] — 2026-05-18

### Fixed — daily 브라우저 History lock 대기 상한

- `collect_browser_history` stage 가 Chrome / Safari / Arc History SQLite lock 에서
  오래 대기하지 않도록 backup 을 별도 Python subprocess 로 실행하고 10초 상한을
  적용한다.
- 상한 초과 시 해당 브라우저만 `errors` 로 기록하고 daily 는 다음 stage 로 계속
  진행한다. 남은 `.tmp` mirror 파일은 즉시 정리한다.
- `daily` 실행 중복 방지 lock, `--only` / `--skip` stage 이름 검증, 부분 실행
  dependency guard 를 추가했다.
- DailyReport 를 최종 elapsed / report stage row 가 반영된 상태로 다시 쓰고,
  collector 내부 `errors=N` 은 `warnings_count` 로 노출한다.
- `synapse-memory daily --watch-status` 를 추가해 실행 중 status 진행률을 같은
  터미널에 한 줄씩 표시한다.
- `daily` skill / command 문서에 `synapse-memory daily-status --watch` 와
  `--skip collect_browser_history` 우회 명령을 추가했다.

## [0.15.1] — 2026-05-18

### Changed — slash 가이드 v0.15 컬렉터 반영

v0.15.0 에서 13종 외부 데이터 수집기를 추가했지만 slash command prompt 들이
구버전 흐름 그대로였다. 사용자가 처음 실행할 때 *어떤 데이터가 mirror 되는지* /
*어떤 권한 / 환경변수가 opt-in 인지* 가이드가 없어 보강한다.

- `commands/onboard.md` — 환경 점검 직후 "1.5단계 — 데이터 수집 범위 안내"
  추가. iMessage(FDA), Gmail(`SYNAPSE_GMAIL_ENABLE`), Apple Health(드롭인)
  한 줄 안내. 첫 세션은 한 줄로만, 사용자가 명시적으로 물어볼 때만 자세히.
- `commands/assistant.md` — 우선순위 규칙 9개로 확장. 8번 신설:
  *우선순위 1~7 이 모두 OK 일 때만* Tier 3/4 opt-in 컬렉터 활성화 검토 안내.
- `commands/daily.md` — 파이프라인 흐름 stage 목록을 17종 컬렉터로 갱신.
  컬렉터별 source 미존재 / 권한 부재가 실패가 아니라는 점 명시.

### Changed — 사용자 문서 최신화

- `docs/README.md` — 추가 흐름 표에 v0.14.0 / v0.15.0 항목 보강.
- `docs/start-here.md` — "어떤 데이터를 수집하나요?" 신규 섹션 추가 (자동 / opt-in
  / 권한 필요 컬렉터 표). 이후 헤더 번호 일괄 +1.
- `docs/privacy-and-cost.md` — 저장 위치 표에 신규 컬렉터 9 행 추가.
  "자동 수집 vs opt-in 컬렉터" 신규 섹션 — 활성화 / 비활성화 방법 표.

### Internal

- pyproject / `__init__.py` / Claude·Codex plugin manifest / README installer URL
  0.15.0 → 0.15.1 동기 bump.

## [0.15.0] — 2026-05-18

### Added — 외부 데이터 수집기 13종 확장 (spec 016)

`~/.synapse/private/raw/` 로 mirror 되는 데이터 소스를 기존 2종(Claude Code,
Obsidian) 에서 15종으로 확장. 각 컬렉터는 source 미존재 / 권한 부재 시 안전하게
skip 하며 (`daily.py` 의 `_run_step` try/except 격리), 모든 SQLite 접근은
`mode=ro` URI 로 source data 무변경 보장.

**Tier 1 — 개발자 활동 5종** (PR #21, v0.14.0 에 이미 포함되어 빌드됨)

- `shell_history` — `~/.zsh_history`, `~/.bash_history` mirror
- `cursor` — Cursor IDE SQLite snapshot
- `continue_dev` — Continue.dev (VS Code) 세션 JSON
- `aider` — Aider 터미널 AI pair 대화

**Tier 2 — 로컬 파일 3종** (PR #22)

- `apple_notes` — Apple Notes `NoteStore.sqlite`
- `day_one` — Day One Journal SQLite
- `vscode_local_history` — VS Code 파일별 auto-snapshot
- 공통 헬퍼 `_sqlite_mirror.py` — `sqlite3.backup` + mtime/sha256 변경 감지

**Tier 3 — PII opt-in 3종** (PR #23)

- `imessage` — iMessage `chat.db` (macOS Full Disk Access 필요)
- `gmail_sent` — Gmail Sent (OAuth, `SYNAPSE_GMAIL_ENABLE` opt-in,
  `google-api-python-client` lazy import 로 미설치 환경 안전)
- `calendar` — macOS Calendar ICS

**Tier 4 — 행동 데이터 3종** (PR #24)

- `browser_history` — Chrome / Safari / Arc History SQLite
- `screen_time` — macOS `knowledgeC.db`
- `apple_health` — iOS Health `export*.zip` drop-in (기본 `~/Downloads`)

### Added — `daily` 파이프라인 stage 확장

`daily.py` `DAILY_STAGES` 에 신규 컬렉터 13 stage 추가. 모두 incremental
(기존 처리분 자동 skip), `--only` / `--skip` / `--resume-from` 호환.

### Internal

- 신규 unit + integration 테스트 (각 컬렉터별 mirror test 모듈 13종)
- 첫 설치 안전성 검토 완료 — source 부재 / 권한 부재 / 3rd-party 미설치
  모두 crash 없이 빈 stats 반환 확인
- spec/plan/tasks: `specs/016-collectors-expansion/`

## [0.14.0] — 2026-05-18

### Added — 로컬 LLM 동작 원리 문서

- `docs/local-llm.md` 추가 — Apple FoundationModel(apfel) 게이트가 어떤 사용자
  시나리오(`/sm:daily`, `/sm:ask`, `/sm:doctor`)에서 어떻게 호출되는지를
  mermaid 다이어그램과 함께 정리. `docs/README.md` 인덱스에 연결.

### Changed — DailyReport Stage Summary 사람 친화 렌더링

`v0.13.x` 까지 Stage Summary 표의 Summary 칼럼이 stdout 로그를 그대로 끼워 넣은
모양(`scanned=252 mirrored=9 bytes+=73888700 truncations=0 skipped_empty=0 errors=0`)
이었다. 운영자가 매일 보는 보고서치고는 노이즈가 많아서, stage 별로 한 문장 요약으로
바꾸었다.

- `collect_claude_code` / `collect_obsidian`: `"Claude 활동 로그 9개 mirror (70.5 MB)"`,
  `"vault 노트 17개 mirror (209.3 KB) · 변경 없음 1348"` 식으로 변환.
  이상치(truncations / skipped_empty / errors > 0) 가 있을 때만 뒤에 표시 — 정상
  케이스는 깔끔하게 유지.
- `index`: `"Project Card 25개, Company Card 3개 인덱싱"`
- `update_profile`: `"Fact 13개, Pattern 13개 → Profile-2026-05-18.md"`
- `classify` / `generate` / `report` 는 이미 한국어 사람 친화 — 그대로 통과.

원시 카운터는 표 아래 `<details>` 토글 블록(`Raw stage counters (디버깅용)`)으로
보존되어, 디버깅이 필요할 때 한 번 펼쳐서 확인 가능.

알 수 없는 stage 나 변환 실패 시 raw 를 그대로 두는 안전한 fallback 동작.

## [0.13.1] — 2026-05-18

### Fixed — 플러그인 manifest 버전 동기화

`v0.13.0` 까지 `release.sh` 가 `pyproject.toml` / `__init__.py` / `README.md` /
`CHANGELOG.md` 만 bump 했기 때문에, Claude Code · Codex 플러그인 설정 화면에는
계속 `0.8.4` 가 표시되는 문제가 있었다. 이번 릴리즈는 manifest 정합성만 맞추는
패치이며 기능 변경은 없다.

- `.claude-plugin/plugin.json` `version`: `0.8.4` → `0.13.1`
- `.codex-plugin/plugin.json` `version`: `0.8.4` → `0.13.1`
- `src/synapse_memory/__init__.py` `__version__`: `0.8.5` → `0.13.1`
  (`pyproject.toml` 과 어긋나 있던 잔여물 정리)

### Changed — release 자동화 보강

- `scripts/release.sh` 에 양쪽 `plugin.json` `version` 필드 자동 bump 단계를
  추가. 다음 릴리즈부터는 manifest drift 가 재발하지 않는다.

## [0.13.0] — 2026-05-17

### Added — Obsidian Graph 시각화 (P1+P2, #015)

vault에 쌓이는 자료를 Obsidian Graph view에서 노드 유형별로 시각적으로 탐방할 수 있게 만드는 첫 단계. node 태그 + MOC + Dataview doctor 체크.

#### node/* frontmatter 태그 (US1)

신규 생성되는 다음 파일들 frontmatter에 자동 부착:

- Card (project/company): `tags: [node/card]`
- MemoryInbox Profile 후보: `tags: [node/profile-update]`
- DailyReport: `tags: [node/daily-report]`

Obsidian Graph view 설정에서 그룹별 색상을 한 번 설정하면 노드 유형이 시각적으로 분리됩니다.

#### `synapse-memory moc` + `/sm:moc` (US2)

`90_System/AI/MOC.md`를 동적 인덱스로 생성·갱신.

- Projects / Companies / Profile updates / Daily reports 각 영역 Dataview 블록
- `<!-- SYNAPSE-MEMORY-MOC START/END -->` marker 사이만 교체 — 사용자 자유 메모 보존
- byte-level idempotent
- 자동 트리거 없음 (Constitution VI Installation Consent)
- Claude Code slash `/sm:moc` + Codex skill `moc`

#### `synapse-memory doctor` Dataview 점검 (US3)

신규 `diagnose_dataview_plugin(vault)` 진단을 doctor에 등록. vault `.obsidian/community-plugins.json`에 `"dataview"` 활성화 여부 검사. 미설치 시 ⚠ + 설치 안내.

### Deferred — Suggested wikilink (US4 P3)

자동 wikilink (`## Suggested links` 섹션) 도입은 본 sprint 범위 외. 이유: cluster 분류가 LLM 기반이라 잘못된 link로 graph noise 양산 위험. node 태그 + MOC만으로 graph가 풍부해진 뒤 별 sprint에서 재검토.

### Internal

- 신규 unit + integration 테스트 11개 (node tags 4 + doctor dataview 3 + MOC generator 4)
- 전체 `pytest` 890 passed (879 → 890)
- spec/plan/tasks: `specs/015-graph-viz/`
- 신규 패키지 `synapse_memory.moc` (1 module)

## [0.12.0] — 2026-05-17

### Added — `/sm:apply-profile` GUI 승인 워크플로 (#014)

`/sm:daily`가 만든 `MemoryInbox/{YYYY}/{MM}/Profile-YYYY-MM-DD.md` 후보를 항목별로 검토하고 승인분만 vault `Profile.md` / `DecisionPatterns.md`에 반영하는 슬래시 흐름.

- Claude Code slash `/sm:apply-profile [date | --all-pending]` + Codex skill `apply-profile`
- AskUserQuestion 4개씩 묶어 Y/N/Edit 항목별 승인 (plan-mode GUI 패턴)
- 승인분만 vault Profile.md (카테고리 섹션) / DecisionPatterns.md (`## Approved Patterns`)에 Edit으로 추가
- 후보 파일 frontmatter `status: pending_review` → `status: applied` + `applied_date` 갱신

### Added — `synapse-memory list-pending-profiles` 보조 CLI

슬래시 prompt가 후보 발견에 사용. 직접 호출도 가능.

- `synapse-memory list-pending-profiles [--vault PATH] [--json]`
- `folders.find_candidate_files` (011 sprint 산출물) 재사용
- recursive scan, `applied` 마감된 후보는 자동 제외
- JSON 모드: 슬래시 prompt가 파싱하기 좋게 `[{date, path, status}, ...]`

### Changed — `/sm:daily` 종료 후 apply 흐름 자동 제안 (#014)

`commands/daily.md` prompt가 update_profile 성공 시 AskUserQuestion으로 "지금 검토할까요?"를 묻습니다. 사용자가 Yes 답해야 진입 — 자동 강제 진입 없음 (Constitution VI Installation Consent 준수). dry-run 또는 update_profile 실패·skip 시 제안 생략.

### Internal

- 신규 test 3개 (`tests/test_cli_list_pending_profiles.py`)
- 전체 `pytest` 879 passed (876 → 879)
- spec/plan/tasks: `specs/014-apply-profile/`
- 신규 코드 최소화 — apply 흐름의 항목 파싱·AskUserQuestion·파일 편집은 모두 슬래시 prompt 안에서 AI가 처리. CLI는 list-pending-profiles 보조 1개만 추가.

## [0.11.0] — 2026-05-17

### Added — `setup` + `sync` CLI: cross-project Profile marker (#013)

다른 프로젝트에서도 Claude Code와 Codex가 vault Profile·Patterns 요약을 인식하도록 `AGENTS.md`/`CLAUDE.md`에 HTML comment marker로 컨텍스트를 삽입한다.

- `synapse-memory setup [--target {agents,claude,both}] [--dry-run]`
  - 현재 cwd 프로젝트의 `AGENTS.md` (Codex 표준) / `CLAUDE.md` (Claude Code 표준)에 `<!-- SYNAPSE-MEMORY START -->` … `<!-- SYNAPSE-MEMORY END -->` 블록 삽입 또는 교체
  - `~/.synapse/projects.yaml` 에 cwd 등록 (`{path, target, registered_at, last_sync, state}`)
  - byte-level idempotent — 같은 vault 상태로 재실행 시 결과 동일
  - marker 외부 라인 보존, unclosed marker fail-closed (종료 코드 1)
- `synapse-memory sync [--current]`
  - 등록된 모든 프로젝트 marker 갱신, `last_sync` 업데이트
  - 등록된 path가 사라진 entry는 `state: stale` 표시 (나머지는 정상 처리)
  - `--current`: cwd 프로젝트만
  - **자동 트리거 없음** — `daily` 같은 다른 명령이 sync를 부르지 않음 (명시 호출만, 사용자 결정 2026-05-17)

### Added — `synapse_memory.projects` 신규 패키지

- `projects.marker`: `MARKER_START`/`MARKER_END` 상수, `inject_or_replace`, `extract_block`, `MarkerParseError`
- `projects.registry`: `ProjectEntry` dataclass, atomic write(`tempfile + os.replace`), `load_registry`/`save_registry`/`upsert_entry`/`mark_stale`
- `projects.summary`: `generate_marker_body(profile, patterns, *, fact_top_n=5, pattern_top_m=4)`

### Slash + Skill

- Claude Code marketplace: `commands/setup.md`, `commands/sync.md`
- Codex skill: `skills/setup/SKILL.md`, `skills/sync/SKILL.md`
- docs: `docs/reference.md` "다른 프로젝트에서 sm 컨텍스트 활용하기" 섹션

### Internal

- 신규 unit + integration 테스트 18개 (marker 6 + registry 4 + summary 3 + CLI 5)
- 전체 `pytest` 876 passed (858 → 876)
- spec/plan/tasks: `specs/013-sm-setup-sync/`

## [0.10.0] — 2026-05-17

### Added — `redact file` CLI + `/sm:redact` 슬래시 (#012)

vault 안의 개인 메모를 외부 AI에 보내기 전 로컬에서 마스킹하기 위한 명령.

- `synapse-memory redact file <path> [--out PATH]`
- Pass 1 (regex + redactlist) + Pass 2 (apfel 로컬 LLM) 통합 적용
- apfel 미설치 환경은 Pass 1 only fallback (regex + redactlist는 그대로 동작) + stderr 경고
- 입력 한도: 1 MB, UTF-8 텍스트만. binary는 skip + 경고
- 종료 코드: `0` = 정상 / `2` = 입력 무효 (파일 없음 / 1 MB 초과 / binary)
- Claude Code 슬래시 `/sm:redact <path>` + Codex skill `redact` 신규 등록

### Added — `synapse-memory doctor` Private 폴더 차단 점검 (#012)

신규 `diagnose_private_folder_deny(vault)` 진단을 doctor 흐름에 추가. vault `90_System/Private/`가 있을 때 `.claude/settings.json` 의 `permissions.deny` 에 다음 3개 패턴이 모두 등록됐는지 검사한다.

- `Read(./90_System/Private/**)`
- `Glob(./90_System/Private/**)`
- `Write(./90_System/Private/**)`

누락 시 ⚠ 경고 + 수정 안내. Private 폴더가 없으면 OK (불필요).

### Docs — Private 폴더 관례 + Codex 격리 정책

`docs/reference.md` 에 "개인 메모를 외부 AI에 안전하게 전달하기" + "Codex 격리 정책" 섹션 추가. `.claudeignore` 는 Claude Code 공식 매커니즘이 아니라 도입하지 않았다 (2026-05-17 spike 검증). Codex 는 강제 차단 기능이 없어 AGENTS.md 가이드 + 작업 디렉터리 sub-folder 분리 권장.

### Internal

- 신규 unit + integration 테스트 11개 (`tests/test_cli_redact_file.py` 7개, `tests/test_doctor_private_check.py` 4개)
- 전체 `pytest` 858 passed (847 → 858)
- spec/plan/tasks: `specs/012-private-permissions/`

## [0.9.0] — 2026-05-17

### Changed — MemoryInbox / DailyReports year/month folder structure (#011)

매일 `synapse-memory daily` 실행으로 누적되는 후보·리포트 파일이 flat하게 쌓여
탐색이 어려운 문제를 해결. 신규 파일은 자동으로 `{YYYY}/{MM}/` 하위 폴더에
생성된다.

- `save_profile_update(profile/extract.py)`: 신규 `date` 키워드 인자 + 경로
  산출에 `synapse_memory.folders.year_month_path` 사용. 결과 경로:
  `MemoryInbox/{YYYY}/{MM}/Profile-{YYYY-MM-DD}.md`
- `write_daily_report(daily.py)`: 동일 패턴 적용. 결과 경로:
  `DailyReports/{YYYY}/{MM}/{YYYY-MM-DD}.md`
- 신규 모듈 `src/synapse_memory/folders/`: `year_month_path()`,
  `find_candidate_files()` (재귀 glob). 다른 모듈도 MemoryInbox·DailyReports
  scan 시 이 helper를 통과해야 함.

### Added — `migrate-folders` CLI (1회성 마이그레이션 도구)

기존 flat 파일이 있는 vault에서 새 구조로 안전하게 옮기는 도구.

- `synapse-memory migrate-folders [--dry-run] [--report-unknown] [--vault PATH]`
- 정규식 매치: `Profile-YYYY-MM-DD.md` (MemoryInbox 전용), `YYYY-MM-DD.md`
  (DailyReports 전용)
- 충돌 시 fail-closed: 대상 파일이 이미 존재하면 이동 안 함, conflict로 보고
- idempotent: 두 번 실행해도 0건 이동
- 종료 코드: `0`=정상 / `1`=충돌 있음 / `2`=시스템 에러

### Breaking — apply-profile / cleanup 등 후속 코드 영향

- MemoryInbox candidate를 읽는 후속 기능(예: apply-profile, cleanup scan)은
  flat 스캔 대신 `folders.find_candidate_files()` 같은 재귀 스캔을 사용해야
  한다. 이번 릴리스에는 기존 cleanup·apply 호출 경로는 변경되지 않았으니
  v0.10.x 작업 전 점검 필요.

### Internal

- 신규 unit + integration 테스트 21개 (`tests/test_folders_*.py`,
  `tests/test_daily_year_month.py`, `tests/test_cli_migrate_folders.py`).
  전체 `pytest` 847 passed.
- spec/plan/tasks: `specs/011-yearmonth-folders/`. 실제 vault migration
  검증 기록: `verification-2026-05-17.md`.

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
