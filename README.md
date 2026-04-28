# Synapse Memory

Synapse Memory는 Claude/Codex 대화를 안전하게 수집해 Obsidian 기반 `MemoryInbox`로 보내고, 사용자가 승인한 후보만 장기 기억으로 반영하는 로컬 우선 AI Memory 플러그인입니다.

이 플러그인의 핵심 원칙은 단순합니다.

- raw/near-raw 대화는 synced 저장소에 두지 않습니다.
- 장기 기억 후보는 guard를 통과한 뒤 `MemoryInbox`에만 기록합니다.
- `Profile.md`, `DecisionPatterns.md`, `DecisionQualityRegistry.md` 반영은 사용자가 명시적으로 실행할 때만 일어납니다.

## 전체 구조

```text
Claude / Codex
  -> local collectors
  -> ~/.synapse/private/normalized
  -> heuristic candidate extraction
  -> Obsidian MemoryInbox
  -> manual approval
  -> explicit reflect command
  -> Profile / DecisionPatterns / DecisionQualityRegistry
```

## 저장 경계

`~/.synapse/private`는 iCloud, Dropbox, Git, Obsidian Vault 같은 synced 저장소로 옮기지 마세요.

```text
로컬 전용:
  ~/.synapse/private/
    queue/
    checkpoints/
    dead-letter/
    normalized/
    redaction-reports/

공유 Vault:
  90_System/AI/
    MemoryInbox/
    Profile.md
    DecisionPatterns.md
    DecisionQualityRegistry.md
```

여러 Mac에서 사용할 때도 각 Mac은 자기 `~/.synapse/private`를 따로 가집니다. 공유되는 것은 iCloud Vault의 `90_System/AI` 장기 기억 계층입니다.

## 포함된 구성

- Claude Code 플러그인 manifest: `.claude-plugin/plugin.json`
- Claude Code marketplace manifest: `.claude-plugin/marketplace.json`
- Claude Code slash commands: `commands/`
- Codex 플러그인 manifest: `.codex-plugin/plugin.json`
- Codex/Claude 공용 skill: `skills/synapse-memory/SKILL.md`
- Obsidian Vault 초기 세팅 skill: `skills/obsidian-vault-setup/SKILL.md`
- 런타임 스크립트: `scripts/`
- 단일 CLI: `scripts/synapse.py`
- 시스템 문서: `docs/Synapse AI Memory 동작 원리.md`

## 빠른 시작

플러그인 루트에서 실행합니다.

```bash
cd /Users/jimmy/Documents/GitHub/synapse-memory
python3 scripts/synapse.py status
python3 scripts/synapse.py bootstrap
python3 scripts/synapse.py install
python3 scripts/synapse.py e2e --dry-run
```

`install`, `review`, `kpi`, `archive` 계열은 기본적으로 dry-run부터 실행하는 흐름을 권장합니다.

## CLI 명령

| 명령 | 역할 |
|---|---|
| `status` | Vault/runtime 경로와 준비 상태 확인 |
| `bootstrap` | 새 Mac의 `~/.synapse` 로컬 런타임 구조 준비 |
| `install` | Claude hook과 LaunchAgent 설치 계획 확인 또는 적용 |
| `e2e` | 임시 workspace에서 end-to-end fixture 실행 |
| `review` | MemoryInbox 후보 검토. 자동승인 없음 |
| `reflect` | approved 후보를 장기 기억으로 반영 |
| `kpi` | counters 기반 일일 KPI 요약 |
| `archive` | normalized store 용량 점검 및 오래된 파일 gzip |
| `vault-setup` | Synapse 방식의 Obsidian Vault 폴더 구조 초기화 |

## Vault 위치 설정

기본 Vault 위치는 다음 경로입니다.

```text
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/90_System/AI
```

다른 Vault를 사용한다면 명령마다 `--vault-ai-root`를 넘깁니다.

```bash
python3 scripts/synapse.py status --vault-ai-root "/path/to/90_System/AI"
```

또는 환경변수로 고정할 수 있습니다.

```bash
export SYNAPSE_VAULT_AI_ROOT="/path/to/90_System/AI"
```

## 새 Mac bootstrap

먼저 생성될 경로를 확인합니다.

```bash
python3 scripts/synapse.py bootstrap
```

문제가 없으면 실제 생성합니다.

```bash
python3 scripts/synapse.py bootstrap --apply
```

생성 대상:

- `~/.synapse/bin`
- `~/.synapse/counters`
- `~/.synapse/logs`
- `~/.synapse/private/queue`
- `~/.synapse/private/checkpoints`
- `~/.synapse/private/backups`
- `~/.synapse/private/dead-letter`
- `~/.synapse/private/normalized`
- `~/.synapse/private/redaction-reports`
- `~/.synapse/private/fixtures`

## Obsidian Vault 초기 세팅

새 Obsidian Vault에 Synapse 방식 폴더 구조를 만들 때 사용합니다.

먼저 dry-run:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault"
```

실제 생성:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --apply
```

생성되는 기본 구조:

```text
00_Inbox/
10_Active/
20_Reference/
30_Creative/
40_Life/
90_System/
99_Archive/
```

### 폴더별 역할

| 폴더 | 역할 | 사용 기준 |
|---|---|---|
| `00_Inbox` | 빠른 캡처 | 아직 분류하지 않은 생각, 링크, 메모를 임시 보관합니다. |
| `10_Active` | 현재 진행 중인 작업 | 지금 실제로 움직이는 프로젝트, 모임, 학습, 글쓰기 작업을 둡니다. |
| `20_Reference` | 재사용 가능한 지식 | 반복해서 참고할 원칙, 패턴, 코드 조각, 주제별 자료를 둡니다. |
| `30_Creative` | 창작 파이프라인 | 초안, 글쓰기 스킬, 발행본처럼 산출물로 발전하는 자료를 둡니다. |
| `40_Life` | 개인 생활 영역 | 돈, 여행, 취미처럼 작업 시스템과 분리해 보고 싶은 생활 정보를 둡니다. |
| `90_System` | Vault 운영 시스템 | 템플릿, 첨부파일, AI Memory, 자동화 문서처럼 Vault를 움직이는 기반을 둡니다. |
| `99_Archive` | 완료/동결 자료 | 끝났거나 더 이상 활성 관리하지 않는 자료를 보존합니다. |

`20_Reference` 하위 폴더는 다음 기준으로 나눕니다.

| 폴더 | 역할 |
|---|---|
| `Principles` | 오래 유지되는 원칙, 판단 기준 |
| `Patterns` | 반복해서 재사용할 작업 방식, 설계 패턴 |
| `Snippets` | 코드/문장/명령어 조각 |
| `Topics` | 특정 주제별 참고 자료 |

`30_Creative` 하위 폴더는 산출물의 진행 상태를 드러냅니다.

| 폴더 | 역할 |
|---|---|
| `Drafts` | 초안 |
| `Skills` | 창작/글쓰기 능력 자체를 개선하는 자료 |
| `Published` | 발행되었거나 외부에 공유한 결과물 |

### 왜 이런 구조를 쓰는가

이 구조는 “주제별 분류”보다 “상태별 흐름”을 우선합니다. 노트가 무엇에 관한 것인지보다 지금 어떤 상태인지가 먼저 보이도록 설계되어 있습니다.

```text
캡처 -> 진행 -> 참조화/창작화 -> 시스템화 -> 보관
00_Inbox -> 10_Active -> 20_Reference / 30_Creative -> 90_System -> 99_Archive
```

이 방식의 장점:

- 새 메모를 어디에 둘지 고민하는 시간을 줄입니다.
- 지금 움직이는 일과 장기 참고 자료가 섞이지 않습니다.
- 끝난 프로젝트를 `99_Archive`로 옮겨도 지식 자산은 `20_Reference`에 남길 수 있습니다.
- AI가 Vault를 읽을 때 “현재 작업”, “참고 지식”, “시스템 규칙”, “보관 자료”를 구분하기 쉽습니다.
- iCloud 동기화 환경에서도 raw 데이터와 승인된 기억의 경계를 분명히 유지할 수 있습니다.

### AI Memory 폴더가 `90_System/AI`에 있는 이유

AI Memory는 일반 노트가 아니라 Vault 운영 시스템의 일부입니다. 그래서 `10_Active`나 `20_Reference`가 아니라 `90_System/AI` 아래에 둡니다.

```text
90_System/AI/
  MemoryInbox/
  Profile.md
  DecisionPatterns.md
  DecisionQualityRegistry.md
  MemoryReview.md
  Policies/
  Schemas/
  Scripts/
  Tests/
  Sessions/
  Prompts/
```

각 폴더와 파일의 역할:

| 경로 | 역할 |
|---|---|
| `MemoryInbox/` | 장기 기억 후보 검토함. 자동 수집 결과는 먼저 여기로 들어옵니다. |
| `Profile.md` | 승인된 사용자 성향/응답 선호 장기 기억 |
| `DecisionPatterns.md` | 승인된 일하는 방식과 의사결정 패턴 |
| `DecisionQualityRegistry.md` | 기억의 근거, TTL, 반박/폐기 이력을 관리 |
| `MemoryReview.md` | 주간/일일 리뷰와 KPI 요약 |
| `Policies/` | raw 저장 금지, redaction, migration 같은 운영 정책 |
| `Schemas/` | `SessionRecord`, `MemoryCandidate` 같은 데이터 스키마 |
| `Scripts/` | Vault 안에서 추적되는 자동화 스크립트 복사본 |
| `Tests/` | guard/collector/reviewer 등 회귀 테스트 |
| `Sessions/` | 승인된 세션 요약 또는 설계 기록 |
| `Prompts/` | 재사용 가능한 프롬프트 자산 |

중요한 경계:

```text
~/.synapse/private       = raw/near-raw, 로컬 전용
90_System/AI/MemoryInbox = 검토 가능한 후보, iCloud 동기화 가능
90_System/AI/Profile.md  = 승인된 장기 기억
```

이 경계를 지키면 여러 Mac에서 같은 Vault를 공유하면서도 raw 대화나 민감정보가 iCloud에 섞이는 일을 막을 수 있습니다.

기본값으로 `90_System/AI` 하위 Memory 폴더도 함께 생성합니다. AI Memory 폴더를 제외하려면:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --without-ai-memory
```

기존 파일은 기본적으로 덮어쓰지 않습니다.

## Claude/Codex 자동화 설치

설치는 항상 dry-run부터 확인합니다.

```bash
python3 scripts/synapse.py install
```

이 명령은 실제 파일을 쓰지 않고 다음을 보여줍니다.

- Claude `SessionEnd` hook script 경로
- LaunchAgent plist 경로 4개
- `~/.claude/settings.json` 변경 여부
- `vault_ai_root`

실제 hook과 LaunchAgent 파일을 쓰려면:

```bash
python3 scripts/synapse.py install --install
```

LaunchAgent까지 즉시 로드하려면:

```bash
python3 scripts/synapse.py install --install --load-agents
```

`--load-agents`는 자동 실행을 켜는 명령입니다. 의도한 경우에만 사용하세요.

## E2E 점검

임시 workspace에서 더미 Claude 대화를 만들어 전체 흐름을 점검합니다.

```bash
python3 scripts/synapse.py e2e --dry-run
```

실제 fixture를 실행하려면:

```bash
python3 scripts/synapse.py e2e
```

이 fixture는 임시 디렉터리를 사용하며 실제 Vault `MemoryInbox`에 쓰지 않습니다.

## MemoryInbox 검토

자동승인은 없습니다. 먼저 dry-run으로 확인합니다.

```bash
python3 scripts/synapse.py review --dry-run
```

확인 항목:

- `reviewed`
- `pending`
- `expired`
- `changed`

dry-run 없이 실행하면 TTL이 지난 `pending` 후보만 `expired`로 바꿀 수 있습니다. `approved`로 바꾸는 동작은 하지 않습니다.

## 장기 기억 반영

장기 기억 반영은 수동 2단계입니다.

1. `MemoryInbox/YYYY-MM-DD.md`에서 후보 행의 `Status`를 `approved`로 직접 변경합니다.
2. `reflect` 명령을 실행합니다.

먼저 preview:

```bash
python3 scripts/synapse.py reflect MC-YYYYMMDD-A-NNN
```

실제 반영:

```bash
python3 scripts/synapse.py reflect MC-YYYYMMDD-A-NNN --apply
```

반영 위치:

| memory_type | 반영 파일 |
|---|---|
| `profile` | `90_System/AI/Profile.md` |
| `decision_pattern` | `90_System/AI/DecisionPatterns.md` |
| `project_context` | `90_System/AI/DecisionPatterns.md` |
| `decision_quality` | `90_System/AI/DecisionQualityRegistry.md` |

## KPI와 보관

일일 counters 요약:

```bash
python3 scripts/synapse.py kpi --dry-run
```

normalized store 용량 점검:

```bash
python3 scripts/synapse.py archive --dry-run
```

기본 정책:

- `~/.synapse/private/normalized`가 1GB를 넘으면 경고합니다.
- 90일 이전 normalized JSON은 gzip 압축 대상입니다.
- dry-run 없이 실행해야 실제 압축합니다.

## Claude Code에서 설치

Claude Code에 marketplace를 추가합니다. GitHub 저장소에는 `.claude-plugin/marketplace.json`이 포함되어 있으므로 `owner/repo` 형식으로 등록합니다.

```text
/plugin marketplace add Jimmy-Jung/synapse-memory
```

플러그인을 설치합니다.

```text
/plugin install synapse-memory@synapse-memory-marketplace
```

설치 후 Claude Code가 재시작을 요구하면 재시작합니다.

사용 가능한 slash commands:

```text
/synapse-memory:synapse-status
/synapse-memory:synapse-bootstrap
/synapse-memory:synapse-install
/synapse-memory:synapse-review
/synapse-memory:synapse-reflect
/synapse-memory:synapse-e2e
```

## Codex에서 설치

Codex에서는 GitHub 저장소를 플러그인 소스로 사용합니다.

```text
https://github.com/Jimmy-Jung/synapse-memory
```

로컬에서 개발하거나 검증할 때는 clone된 저장소에서 CLI를 직접 실행해도 됩니다.

```bash
cd /Users/jimmy/Documents/GitHub/synapse-memory
python3 scripts/synapse.py status
```

## 롤백

자동화를 끄고 설정을 복원하려면:

```bash
~/.synapse/bin/rollback.sh --dry-run
~/.synapse/bin/rollback.sh
```

롤백은 LaunchAgent와 Claude settings를 되돌리는 용도입니다. `~/.synapse/private`의 queue, normalized, dead-letter 데이터는 삭제하지 않습니다.

## 포함하지 않는 것

이 플러그인은 다음 데이터를 포함하지 않습니다.

- raw conversations
- normalized private records
- redaction reports
- user-specific queue payloads
- dead-letter payloads

위 데이터는 각 Mac에서 `~/.synapse/private` 아래에 생성됩니다.

## 불변 조건

- `~/.synapse/private`는 로컬 전용입니다.
- raw/near-raw 대화는 Vault에 쓰지 않습니다.
- 자동승인은 없습니다.
- 장기 기억 반영은 `reflect --apply`에서만 일어납니다.
- Claude/Codex 설치는 dry-run 후 명시적으로 적용합니다.
