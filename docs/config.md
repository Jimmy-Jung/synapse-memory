# Config 레퍼런스

> 사용자 설정 파일 — `~/.synapse/config.yaml`
> 슬래시 진입: [`/synapse-config`](../commands/synapse-config.md) (자연어 변경)
> CLI 진입: `synapse-memory config {show,get,set,edit,reset,validate}`

## 어떤 카테고리에 어느 절을 보면 되나

| 카테고리 | 어디 |
|---|---|
| "vault / ai_provider" 같은 최상위 키 | [§ 최상위](#최상위) |
| 작업별 AI 모델 (claude / codex) | [§ models](#models----작업별-ai-모델) |
| RAG 검색 결과 개수 | [§ top_k](#top_k----rag-검색-결과-개수) |
| Cleanup 임계값 | [§ cleanup](#cleanup----vault-청소-임계값) |
| Profile 추출 / 비용 / 가드 / 자동화 | [§ profile · cost · interactive_guard · automation](#profile--cost--interactive_guard--automation) |
| Advanced (RAG·LLM 내부 튜닝) | [§ advanced](#advanced----rag--llm-내부-튜닝-경고-후-변경) |
| 절대 변경 불가 키 | [§ 보호된 키](#-보호된-키--config-노출-안-됨) |

## 우선순위 (12-factor 변형)

```
CLI 인자  >  환경변수  >  ~/.synapse/config.yaml  >  코드 default
```

- CLI 인자가 명시되면 그게 절대 우선 (한 번만 적용)
- env(`SYNAPSE_OBSIDIAN_VAULT`, `SYNAPSE_AI_PROVIDER`, `SYNAPSE_L0_ROOT`, `SYNAPSE_FROM_AGENT`)는 셸 단위 override
- 그 다음 yaml 값을 default로 사용 (사용자 영구 설정)
- 아무것도 없으면 코드의 dataclass default

## 카테고리

| 등급 | 의미 | 변경 방법 |
|---|---|---|
| **A** | 자유 변경 | `config set` 또는 `/synapse-config` |
| **C** | advanced — 잘못 바꾸면 검색 품질 저하 / 색인 재생성 필요 | `config set --force` (경고 후 진행) |
| **D** | 보안 핵심 — 코드 PR로만 변경 | config로 변경 불가 (set 시 차단) |

---

## 최상위

| 키 | default | 타입 | 등급 | 의미 |
|---|---|---|---|---|
| `vault` | `null` (env 의존) | `str?` | A | Obsidian vault 절대 경로. 변경 즉시 새 vault 사용. **기존 vault의 카드는 자동으로 옮겨지지 않음** — 직접 이동 필요 |
| `ai_provider` | `claude` | `claude` / `codex` / `auto` | A | 외부 AI 호출 시 사용할 provider. `auto`면 detect_ai_environment가 자체 결정 |

## models — 작업별 AI 모델

`ai_provider` 값에 따라 `models.claude.*` 또는 `models.codex.*`가 적용됩니다. `auto`이면 detect_ai_environment가 자체 default로 폴백.

| 키 | default (claude) | default (codex) | 의미 |
|---|---|---|---|
| `models.claude.classify` / `models.codex.classify` | `haiku` | `gpt-5.4` | cluster 분류용. 단순 작업이라 가벼운 모델 권장 |
| `models.claude.card_generate` / `models.codex.card_generate` | `sonnet` | `gpt-5.4` | 카드 생성용. YAML 출력 안정성 위해 sonnet 이상 권장 |
| `models.claude.ask` / `models.codex.ask` | `null` | `null` | `/synapse-ask` 답변용. null = provider default |
| `models.claude.decide` / `models.codex.decide` | `null` | `null` | `/synapse-decide` 권장 생성 |
| `models.claude.resume` / `models.codex.resume` | `null` | `null` | `/synapse-resume` 이력서 작성. **opus 권장** (글쓰기 품질) |
| `models.claude.recall` / `models.codex.recall` | `null` | `null` | `/synapse-recall` 시간순 회상 |
| `models.claude.update_profile` / `models.codex.update_profile` | `null` | `null` | `me update-profile` 후보 추출 |

**비용 감각 (Claude 기준)**:
- haiku ≪ sonnet (약 3배) ≪ opus (sonnet 대비 약 5배)

## top_k — RAG 검색 결과 개수

| 키 | default | 범위 | 의미 |
|---|---|---|---|
| `top_k.ask` | 5 | 1~50 | `/synapse-ask`가 가져오는 관련 카드 수 |
| `top_k.recall` | 8 | 1~50 | `/synapse-recall` 시간순 회상 카드 수 |
| `top_k.decide` | 6 | 1~50 | `/synapse-decide` 의사결정 컨텍스트 카드 수 |
| `top_k.resume` | 6 | 1~50 | `/synapse-resume` 이력서 매칭 프로젝트 카드 수 |
| `top_k.rag_search` | 5 | 1~50 | `rag search` 디버그용 결과 수 |

> 늘리면 답변 컨텍스트 풍부 + 비용·시간 증가. 일반적으로 5~10이 적절.

## cleanup — vault 청소 임계값

`/synapse-cleanup`이 사용할 임계값. 모두 days 단위.

| 키 | default | 의미 |
|---|---|---|
| `cleanup.inbox_stale_days` | 30 | `00_Inbox/` 안 파일이 N일 이상 미수정이면 archive 후보 |
| `cleanup.dormant_project_days` | 90 | `10_Active/<회사>/<프로젝트>/` 모든 파일이 N일 변경 없으면 archive |
| `cleanup.old_resume_days` | 90 | `30_Creative/Drafts/Resume - *.md` N일 경과 |
| `cleanup.stale_memory_inbox_days` | 60 | `MemoryInbox/Profile-*.md` 옮겨지지 않은 후보 |
| `cleanup.old_daily_reports_days` | 90 | `DailyReports/*.md` 오래된 리포트 |

> 변경 후 다음 `/synapse-cleanup`부터 새 임계값 적용. 기존 archive에는 영향 없음.

## profile · cost · interactive_guard · automation

| 키 | default | 의미 |
|---|---|---|
| `profile.sample_lines` | 200 | `me update-profile`이 분석할 raw 줄 수. 늘리면 후보 정확도 ↑, 비용·시간 ↑ |
| `cost.summary_days` | 30 | `/synapse-cost` 기본 윈도우 (일) |
| `cost.monthly_cap_usd` | `null` | 월 한도 USD. 초과 시 ask/me 계열 호출 차단 (null = 무제한) |
| `interactive_guard.enabled` | `true` | 사람 직접 CLI 호출 시 3초 안내 표시 여부. 자동화 환경에서 끄면 편리 |
| `interactive_guard.delay_seconds` | 3 | 위 안내 대기 시간 |
| `automation.codex_poller.enabled` | `true` | launchd `net.synapse.codex-poller` 데몬 동작 토글. 변경 후 `synapse-memory install-agent` 재실행 필요 (미구현) |
| `automation.daily_cron.enabled` | `false` | 매일 자동 `daily` 실행 여부 |
| `automation.daily_cron.time` | `"08:00"` | 자동 실행 시각 (24h `"HH:MM"`) |

## advanced — RAG · LLM 내부 튜닝 (경고 후 변경)

⚠️ 잘못 변경하면 검색 품질 저하 또는 색인 재생성 필요. `set --force` 명시 필요.

| 키 | default | 의미 |
|---|---|---|
| `advanced.rag.rrf_k` | 60 | Reciprocal Rank Fusion 가중치. dense + BM25 결합 시 사용. 일반적으로 60이 적정 |
| `advanced.rag.embedding_model` | `bge-m3` | 카드 임베딩 모델. **변경 즉시 전체 색인 재생성 필요** (`rag index --rebuild`) |
| `advanced.llm.claude_timeout_seconds` | 60 | Claude Code 호출 타임아웃 |
| `advanced.llm.codex_timeout_seconds` | 240 | Codex 호출 타임아웃. Codex가 일반적으로 더 김 |

## 🔒 보호된 키 — config 노출 안 됨

코드에서 강제되며 set 시도 시 거부. **보안 핵심 — 코드 PR로만 변경**.

| 키 | 이유 |
|---|---|
| `storage.l0_permissions` | L0 폴더 권한 `0700` 강제 — 보안 1번 규칙 |
| `redaction.pass1_patterns` | 정규식 패턴 — 마스킹 정확도 핵심 |
| `redaction.pass2_enabled` | Pass 2 비활성화 시 *문맥 의존 PII가 외부 누출* — 옵트아웃 금지 |
| `cleanup.protected_paths` | `Profile.md` / `DecisionPatterns.md` / `recipes/` 자동 이동 방지 |

## 관리 명령

| 명령 | 동작 |
|---|---|
| `synapse-memory config show [--advanced] [--json]` | 현재 효력 있는 값 출력. advanced는 기본 숨김 |
| `synapse-memory config get <path>` | 단일 키 조회 (예: `cleanup.inbox_stale_days`) |
| `synapse-memory config set <path> <value> [--force]` | 단일 키 설정. advanced 키는 `--force` 필요 |
| `synapse-memory config edit` | `$EDITOR`로 yaml 직접 편집 (없으면 안내) |
| `synapse-memory config reset [<path>]` | 전체 또는 단일 키를 default로 복원 |
| `synapse-memory config validate` | 타입·범위·알려진 키 검증 |
| `/synapse-config` | Claude/Codex 안에서 자연어 변경 (예: "cleanup inbox 60일로") |

## yaml 예시 — `~/.synapse/config.yaml`

```yaml
# vault — Obsidian 절대 경로
vault: /Users/me/iCloud Drive/SynapseVault

ai_provider: claude   # claude | codex | auto

models:
  claude:
    classify: haiku
    card_generate: sonnet
    ask: null         # null = provider default (sonnet)
    decide: null
    resume: opus      # 이력서는 비싸지만 정교
    recall: null
    update_profile: null
  codex:
    classify: gpt-5.4
    card_generate: gpt-5.4
    ask: null
    decide: null
    resume: null
    recall: null
    update_profile: null

top_k:
  ask: 5
  decide: 6
  recall: 8
  resume: 6
  rag_search: 5

cleanup:
  inbox_stale_days: 30
  dormant_project_days: 90
  old_resume_days: 90
  stale_memory_inbox_days: 60
  old_daily_reports_days: 90

profile:
  sample_lines: 200

cost:
  summary_days: 30
  monthly_cap_usd: 20   # 월 $20 한도 — 초과 시 ask/me 호출 차단

interactive_guard:
  enabled: true
  delay_seconds: 3

automation:
  codex_poller:
    enabled: true
  daily_cron:
    enabled: false
    time: "08:00"

# advanced — 변경 시 --force 필요
# advanced:
#   rag:
#     rrf_k: 60
#     embedding_model: bge-m3
#   llm:
#     claude_timeout_seconds: 60
#     codex_timeout_seconds: 240
```

## 백업과 롤백

매 `set` 호출마다 자동 백업이 생성됩니다.

```
~/.synapse/config.yaml.bak-20260513-143022
```

롤백:

```bash
cp ~/.synapse/config.yaml.bak-<TIMESTAMP> ~/.synapse/config.yaml
```

또는 전체 default로 복원:

```bash
synapse-memory config reset
```

## 환경변수 (env override)

| env | 매핑 | 우선순위 |
|---|---|---|
| `SYNAPSE_OBSIDIAN_VAULT` | `vault` 키 override | env > config |
| `SYNAPSE_AI_PROVIDER` | `ai_provider` 키 override | env > config |
| `SYNAPSE_L0_ROOT` | `storage.l0_root` (advanced, 노출 안 됨) | env > 코드 default |
| `SYNAPSE_FROM_AGENT` | 슬래시 명령이 자동 설정 — interactive guard 우회 | (특수) |

## 더 알아보기

- [용어집](glossary.md) — 키에 등장하는 개념 정의
- [/synapse-config 슬래시](../commands/synapse-config.md) — 자연어 변경 흐름
- [아키텍처 — 4단계 메모리 모델](architecture.md#4단계-메모리-모델) — `storage.*` 키들이 왜 보호되는지
