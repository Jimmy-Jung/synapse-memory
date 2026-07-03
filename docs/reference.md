# 명령과 문제 해결

작성자: JunyoungJung  
작성일: 2026-05-13

이 문서는 매일 쓰는 명령과 문제가 생겼을 때의 순서를 모아둔 참고 문서입니다. 모든
옵션을 외우기보다 "지금 무엇을 하려는가"에서 출발하면 됩니다.

## 먼저 기억할 세 명령

| 상황 | Claude Code | Codex | 터미널 |
| --- | --- | --- | --- |
| 환경이 정상인지 확인 | `/sm:doctor` | `$doctor` | `synapse-memory doctor` |
| 새 자료 정리 | `/sm:daily` | `$daily` | `synapse-memory daily --quick` |
| 내 자료에 질문 | `/sm:ask "질문"` | `$ask "질문"` | `synapse-memory ask "질문"` |

처음에는 이 세 개만으로 충분합니다.

Codex TUI의 Plugins 브라우저에는 custom git marketplace가 표시되지 않을 수 있습니다.
그래도 `$ask`처럼 `$`로 skill을 검색했을 때 `ask (sm)`가 보이면 사용할 수 있습니다.
아래 명령에 출력이 있으면 `sm:*` skill은 모델 입력에도 로드된 상태입니다.

```bash
codex plugin list | grep 'sm@synapse-memory-marketplace'
codex debug prompt-input \
  --disable apps --disable memories --disable chronicle --disable multi_agent \
  "Synapse Memory plugin visibility check" \
  | grep "synapse-memory-marketplace/sm"
```

plugin update 직후 기존 Codex 세션에는 이전 skill 목록이 남을 수 있으므로 새 세션에서
확인합니다.

## 오늘 할 일을 추천받기

```text
/sm:assistant
```

Codex에서는 `$assistant`를 실행합니다. 현재 상태를 읽고 다음 작업을 제안합니다.

- 마지막 daily가 오래됐는지
- MemoryInbox에 검토할 후보가 있는지
- draft 카드나 이력서 초안이 쌓였는지
- 환경 진단이 필요한지

추천을 보고 번호로 고르거나 직접 지시하면 됩니다.

## daily: quick과 full

`daily`는 새 노트와 작업 기록을 정리하는 핵심 흐름입니다.

| 모드 | 언제 쓰나 | 명령 |
| --- | --- | --- |
| quick | 처음 체험, 매일 가벼운 갱신 | `synapse-memory daily --quick` |
| full | 주 1회 정리, Profile 후보 생성, 큰 변경 후 재정리 | `synapse-memory daily` |

quick과 full을 동시에 실행하지 마세요. 둘 다 같은 vault 자료를 갱신하므로 한 번에 하나만
실행하는 것이 안전합니다.

진행 상황은 다음 명령으로 봅니다.

```bash
synapse-memory daily-status
synapse-memory daily-status --watch
```

## 질문하기

```text
/sm:ask "TCA를 왜 도입했지?"
/sm:ask "최근 이력서에 넣을 만한 성과를 찾아줘"
```

Codex에서는 `$ask`를 씁니다.

```text
$ask "TCA를 왜 도입했지?"
$ask "최근 이력서에 넣을 만한 성과를 찾아줘"
```

터미널에서는 다음과 같습니다.

```bash
synapse-memory ask "TCA를 왜 도입했지?"
```

답이 부실하면 보통 두 가지 중 하나입니다.

1. 아직 카드가 충분히 만들어지지 않았습니다. `daily --quick` 또는 full `daily`를 실행합니다.
2. 노트가 `10_Active/<회사>/<프로젝트>/` 같은 프로젝트 폴더에 모여 있지 않습니다.

## 과거 생각 회상

```text
/sm:recall "AI 코딩 도구"
```

Codex에서는 `$recall "AI 코딩 도구"`를 실행합니다.

터미널에서는 다음과 같습니다.

```bash
synapse-memory persona what-did-i-think "AI 코딩 도구"
```

시간순 변화가 중요하면 다음 옵션을 씁니다.

```bash
synapse-memory persona what-did-i-think "AI 코딩 도구" --timeline
```

## 의사결정 도움

```text
/sm:decide "이번 PR을 하나로 낼까 기능 단위로 나눌까?"
```

Codex에서는 `$decide "이번 PR을 하나로 낼까 기능 단위로 나눌까?"`를 실행합니다.

터미널에서는 다음과 같습니다.

```bash
synapse-memory persona decide "이번 PR을 하나로 낼까 기능 단위로 나눌까?"
```

Profile과 DecisionPatterns가 비어 있으면 일반 조언에 가까워집니다. `MemoryInbox` 후보를
검토해 승인된 자료를 늘릴수록 답이 사용자에게 맞춰집니다.

## 이력서 초안

```text
/sm:resume examplecorp
```

Codex에서는 `$resume examplecorp`를 실행합니다.

터미널에서는 다음과 같습니다.

```bash
synapse-memory persona draft-resume examplecorp
```

결과는 Obsidian vault의 `30_Creative/Drafts/`에 생성됩니다. 제출 전에 문장, 수치,
회사명, 민감정보를 직접 확인하세요.

## MemoryInbox 검토

`daily`나 `persona ingest`는 Profile 후보를 바로 확정하지 않고 `MemoryInbox`에 둡니다. 후보 파일은 년·월별 폴더로 정리됩니다 (v0.9.0+).

```text
90_System/AI/MemoryInbox/
└ 2026/05/
   └ Profile-2026-05-17.md
```

같은 구조가 `DailyReports`에도 적용됩니다.

```text
90_System/AI/DailyReports/
└ 2026/05/
   └ 2026-05-17.md
```

검토 순서는 단순합니다.

1. 후보 문장을 읽습니다.
2. 맞는 내용만 `90_System/AI/Profile.md` 또는 `DecisionPatterns.md`로 옮깁니다.
3. 애매하거나 틀린 내용은 옮기지 않습니다.

승인한 자료만 회상, 의사결정, 이력서 초안에 사용됩니다.

## Obsidian Graph 시각화 — `/sm:moc` + node 태그

vault에 쌓이는 자료(Card / Profile 후보 / DailyReport)를 Obsidian Graph view에서 노드 유형별로 둘러보고, 어디를 보완할지 시각적으로 찾는 흐름.

### node 색상 그룹

신규 생성되는 다음 파일들 frontmatter에 자동 부착되는 태그:

| 파일 유형 | 태그 |
|---|---|
| Project / Company Card | `node/card` |
| MemoryInbox Profile 후보 | `node/profile-update` |
| DailyReport | `node/daily-report` |

Obsidian → Graph view → 설정 → Groups에 다음을 추가하면 노드 유형별 색상이 분리됩니다.

```
tag:#node/card             → 색 A
tag:#node/profile-update   → 색 B
tag:#node/daily-report     → 색 C
```

### MOC (Map of Contents)

`/sm:moc` 또는 `synapse-memory moc` 호출 → `90_System/AI/MOC.md` 생성·갱신. Dataview 블록으로 Projects / Companies / Profile updates / Daily reports 각 영역의 최신 항목을 동적 인덱스로 표시.

```bash
synapse-memory moc                    # config의 vault 사용
synapse-memory moc --vault /path/to/vault
```

- marker 사이만 교체 — 사용자가 MOC.md에 추가한 자유 메모는 보존
- byte-level idempotent (같은 vault 상태로 재실행 시 결과 동일)
- 자동 트리거 없음 — daily 등 다른 명령이 MOC를 자동 갱신하지 않음

### Dataview 의존성

MOC 동적 인덱스는 **Dataview 플러그인 필수**입니다. 미설치 시 MOC.md 본문은 그대로 보이지만 데이터 영역은 빈 화면. `synapse-memory doctor` 가 자동으로 점검:

```
✗ Dataview 플러그인 미설치 — MOC.md의 동적 인덱스가 동작하지 않습니다.
  Obsidian → Settings → Community plugins → 'Dataview' 검색 후 설치·활성화.
```

설치 안내대로 Obsidian에서 1회 설정하면 doctor의 ⚠ 가 사라집니다.

## Profile 후보 GUI 승인 — `/sm:apply-profile`

`/sm:daily`가 만든 `MemoryInbox/{YYYY}/{MM}/Profile-YYYY-MM-DD.md` 후보를 항목별로 검토하고 승인분만 vault `Profile.md` / `DecisionPatterns.md`에 반영합니다.

```bash
/sm:apply-profile                  # 가장 최근 pending 후보
/sm:apply-profile 2026-05-17       # 특정 날짜
/sm:apply-profile --all-pending    # 오래된 순으로 전부
```

### 흐름

1. 슬래시 호출 → `synapse-memory list-pending-profiles --json` 으로 pending 목록 조회
2. 후보 파일 Read → ProfileFact + DecisionPattern 항목 평탄화
3. AskUserQuestion 4개씩 (Yes / No / Edit)
4. 승인분 → Profile.md / DecisionPatterns.md에 Edit으로 추가
5. 후보 파일 frontmatter `status: pending_review` → `status: applied` + `applied_date` 갱신

### `/sm:daily` 종료 후 자동 제안

daily가 정상 종료되고 `update_profile`이 성공하면 prompt가 자동으로 apply 흐름을 제안합니다. 사용자가 Yes 답할 때만 진입 — 강제 트리거 없음.

### 보조 CLI

```bash
# pending 후보 목록만 보기
synapse-memory list-pending-profiles
synapse-memory list-pending-profiles --json   # 슬래시 prompt가 파싱
```

`applied` 마감된 후보는 list-pending 결과에서 자동 제외됩니다 (idempotent — apply 흐름 다시 호출 안 됨).

## 다른 프로젝트에서 sm 컨텍스트 활용하기

다른 프로젝트 디렉터리에서도 Claude Code/Codex가 vault Profile·Patterns 요약을 자연스럽게 인식하게 만들 수 있습니다. `synapse-memory setup` 명령은 기본적으로 repo 파일을 수정하지 않고 현재 프로젝트를 `~/.synapse/projects.yaml`에 등록합니다. marker 파일이 필요한 경우에만 `--target`을 지정합니다.

```bash
# 새 프로젝트 디렉터리에서 1회 실행
cd ~/proj/my-ios-app
synapse-memory setup                    # repo 파일 수정 없이 hook 등록
synapse-memory setup --target both      # AGENTS.md + CLAUDE.md marker
synapse-memory setup --target agents    # AGENTS.md만 (Codex 전용)
synapse-memory setup --target claude    # CLAUDE.md만 (Claude Code 전용)
synapse-memory setup --dry-run          # 변경 미리보기
```

marker 형식 (HTML 주석이라 마크다운 렌더링 시 비가시):

```text
<!-- SYNAPSE-MEMORY START -->
## Second Brain (Synapse Memory)

Profile: /Users/jimmy/.../Profile.md
Patterns: /Users/jimmy/.../DecisionPatterns.md

명령: `/sm:recall <topic>` · `/sm:ask <질문>` 으로 사용자 자료를 조회.

### Quick reference

**Facts**
- ...

**Decision patterns**
- ...
<!-- SYNAPSE-MEMORY END -->
```

마커 외부 라인은 그대로 보존됩니다. 같은 vault 상태에서 setup을 두 번 실행하면 결과 파일은 byte-level 동일입니다 (idempotent).

### marker 갱신 — sync

vault `Profile.md` 또는 `DecisionPatterns.md` 가 바뀐 뒤에 등록된 프로젝트들의 marker도 새 내용으로 갱신하려면:

```bash
synapse-memory sync              # 등록된 모든 프로젝트 갱신
synapse-memory sync --current    # 현재 디렉터리 프로젝트만 갱신
```

- 자동 트리거 없음. `synapse-memory daily` 같은 다른 명령이 sync를 자동 호출하지 않습니다.
- 등록된 path가 사라진 entry는 `state: stale` 로 표시되고, 나머지는 정상 처리됩니다.

### registry 위치

`~/.synapse/projects.yaml` 에 다음 스키마로 저장됩니다.

```yaml
version: 1
projects:
  - path: /Users/jimmy/proj/my-ios-app
    target: both              # both | agents | claude
    registered_at: 2026-05-17
    last_sync: 2026-05-17
    state: active             # active | stale
```

## 개인 메모를 외부 AI에 안전하게 전달하기

vault 안에 외부 AI가 직접 읽으면 안 되는 개인 메모가 있다면 `90_System/Private/` 폴더를 관례로 사용합니다. Claude Code는 vault `.claude/settings.json` 의 `permissions.deny` 로 차단합니다.

```json
{
  "permissions": {
    "deny": [
      "Read(./90_System/Private/**)",
      "Glob(./90_System/Private/**)",
      "Write(./90_System/Private/**)"
    ]
  }
}
```

`synapse-memory doctor` 가 자동으로 점검합니다. Private 폴더가 있는데 위 세 deny 패턴이 빠지면 ⚠ 경고가 표시됩니다.

### Codex 격리 정책

Codex CLI 는 Claude Code 의 `permissions.deny` 와 동등한 차단 매커니즘이 없습니다. 다음 두 가지 정책 기반 가드를 권장합니다.

1. vault 루트 또는 `~/.codex/AGENTS.md` 헤더에 명시:
   > Codex MUST NOT access `90_System/Private/` and MUST NOT read or quote files under that folder.
2. Codex 실행 시 작업 디렉터리를 vault 루트가 아닌 sub-folder (예: `10_Active/<project>/`) 로 잡습니다. Codex 의 sandbox 정책이 작업 디렉터리 밖 접근을 막아줍니다.

## 기존 vault를 새 폴더 구조로 옮기기 (1회성)

v0.8.x까지는 `MemoryInbox/Profile-YYYY-MM-DD.md`와 `DailyReports/YYYY-MM-DD.md`가 flat하게 쌓였습니다. v0.9.0부터 자동으로 `{YYYY}/{MM}/` 하위에 생성되며, 기존 flat 파일은 `migrate-folders` 명령으로 옮길 수 있습니다.

```bash
# 먼저 의도된 이동만 확인
synapse-memory migrate-folders --dry-run --report-unknown

# 실제 이동
synapse-memory migrate-folders
```

| 옵션 | 의미 |
| --- | --- |
| `--dry-run` | 실제 이동 없이 의도된 이동 리스트만 출력 |
| `--report-unknown` | 패턴(`Profile-YYYY-MM-DD.md` 또는 `YYYY-MM-DD.md`)에 맞지 않아 건너뛴 파일 목록 표시 |
| `--vault PATH` | vault 경로 override (기본: 설정값) |

종료 코드: `0`=정상 / `1`=충돌(기존 파일 존재) / `2`=시스템 에러(vault 경로 없음 등).

명령은 idempotent합니다. 두 번 실행해도 안전합니다. 충돌이 생기면 원본은 그대로 두고 사용자가 직접 정리해야 합니다.

## 설정 바꾸기

Claude Code에서는 slash 명령으로 요청할 수 있습니다.

```text
/sm:config cleanup inbox를 60일로 바꿔줘
/sm:config ask 결과는 8개로 보여줘
```

Codex에서는 `$config`를 씁니다.

```text
$config cleanup inbox를 60일로 바꿔줘
$config ask 결과는 8개로 보여줘
```

터미널에서는 직접 설정합니다.

```bash
synapse-memory config show
synapse-memory config set cleanup.inbox_stale_days 60
synapse-memory config set top_k.ask 8
synapse-memory config validate
```

설정 변경은 자동 백업을 남깁니다. 보안 핵심 키는 설정 명령으로 바꿀 수 없습니다.

### vault 폴더 이름 바꾸기

Synapse가 쓰는 vault 내부 폴더는 `~/.synapse/config.yaml`의 `vault_folders`에서
바꿀 수 있습니다. 기본값은 기존 PARA 구조를 유지합니다.

예를 들어 archive 폴더를 `99_Archive`로 통일하려면 다음처럼 설정합니다.

```yaml
vault: /Users/me/Obsidian/Vault
vault_folders:
  archive: 99_Archive
  system:
    ai:
      cleanup_reports: 99_Archive/CleanupReports
```

이후 `synapse-memory config validate`로 설정을 확인하세요. `cleanup`은 오래된 노트를
`99_Archive/_cleanup-YYYY-MM-DD/`로 이동하고, cleanup report도 위 경로에 씁니다.

## 비용 확인

```bash
synapse-memory cost summary --days 30 --by command
synapse-memory cost summary --days 7 --by model
```

비용이 커졌다면 먼저 full `daily`가 너무 자주 돌고 있지 않은지, 같은 질문을 반복하고
있지 않은지 확인합니다.

## vault 정리

오래된 초안이나 검토하지 않은 후보가 쌓였을 때 사용합니다.

```text
/sm:cleanup
```

Codex에서는 `$cleanup`을 실행합니다.

터미널에서는 먼저 scan으로 후보만 확인합니다.

```bash
synapse-memory cleanup scan
```

실제 정리는 archive 폴더로 이동하는 방식입니다. 중요한 노트는 삭제하지 않습니다.

## 문제가 생겼을 때

순서는 고정입니다.

1. Claude Code `/sm:doctor`, Codex `$doctor`, 또는 `synapse-memory doctor`
2. Claude Code `/sm:fix`, Codex `$fix`, 또는 `synapse-memory doctor --fix`
3. Obsidian vault 경로 확인
4. `synapse-memory config validate`
5. 그래도 안 되면 GitHub Issues에 doctor 출력과 상황을 남깁니다.

vault 경로가 틀렸다면 다음 흐름으로 확인합니다.

```bash
synapse-memory config show
synapse-memory doctor --fix-config
```

## 외부 데이터 수집기 (Collectors v2)

`/sm:daily` 가 매번 호출하는 입력 mirror 단계. 모든 데이터는 로컬
``~/.synapse/private/raw/`` 에 먼저 저장되며, mirror/collect 단계 자체는 외부 AI를
호출하지 않습니다. 이후 wiki 통합 단계(`ingest`/`backfill`/`watch`)에서는 small raw
또는 sampled raw가 설정된 provider로 갈 수 있습니다.

| 수집기 | 소스 | 기본 켜짐 | 비고 |
|---|---|:---:|---|
| `collect_claude_code` | `~/.claude/projects/<slug>/<id>.jsonl` | ✅ | Claude Code 세션 |
| `collect_codex` | `~/.codex/sessions/.../*.jsonl` + `history.jsonl` | ✅ | Codex CLI |
| `collect_cursor` | Cursor IDE `state.vscdb` (SQLite) | ✅ | macOS 표준 경로 |
| `collect_continue` | `~/.continue/sessions/*.json` | ✅ | Continue.dev VS Code 확장 |
| `collect_aider` | `~/.aider.chat.history.md`, `.input.history` | ✅ | terminal AI pair |
| `collect_day_one` | `~/Library/Group Containers/<TEAM_ID>.dayoneapp2/` | ✅ | `SYNAPSE_DAYONE_HOME` override 가능 |
| `collect_gmail_sent` | Gmail API (Sent 라벨) | ⛔ opt-in | `SYNAPSE_GMAIL_ENABLE=1` + OAuth credentials 필요 |
| `collect_obsidian` | Obsidian vault `*.md` | ✅ | iCloud Obsidian 기본 |

Apple Health, Apple Notes, Browser History, Calendar, iMessage, Screen Time, Shell
History, VS Code Local History, `git_self` collector는 v1.20.0에서 제거됐습니다.

### `collect_gmail_sent` 켜기

Gmail Sent 라벨 메타 (subject, snippet, label_ids) 만 JSONL mirror. 본문은
저장하지 않습니다.

```bash
# 1. Google Cloud Console 에서 OAuth 2.0 client ID (Desktop) 생성 후
#    credentials.json 다운로드 → 다음 경로에 두기 (또는 env override)
mkdir -p ~/.config/synapse-memory
mv ~/Downloads/credentials.json ~/.config/synapse-memory/gmail-credentials.json

# 2. Python 의존성 (optional)
pip install google-api-python-client google-auth-oauthlib

# 3. opt-in env
export SYNAPSE_GMAIL_ENABLE=1

# 4. 다음 daily 실행에서 OAuth browser flow 1회 (token 캐시됨)
/sm:daily
```

token cache 는 `~/.config/synapse-memory/gmail-token.json`. refresh token 으로
이후 호출 자동 갱신.

## ingest / backfill / watch (엔진 명령)

`daily`와 watch 데몬이 내부적으로 쓰는 저수준 명령입니다. 보통 직접 쓸 일은 없습니다.

- `synapse-memory ingest --now --source claude-code` / `--source codex`
  raw 대화를 wiki 페이지로 통합. `--source`는 `claude-code`와 `codex`를 받습니다.
- `synapse-memory ingest-audit --source codex --limit 50`
  watermark 이후 pending raw queue를 LLM 호출 없이 점검합니다. 출력의
  `estimated_llm_calls`, `sampled`, `oversize`, `max_chars`로 backfill 비용과 jam
  위험을 먼저 확인합니다. 출력에는 `privacy_mode=raw_or_sampled_raw_to_provider`와
  `provider_payload=small_raw_or_sampled_raw`도 함께 표시되어, small raw 전체 또는
  sampled raw 일부가 provider로 갈 수 있음을 실행 전 확인할 수 있습니다.
- `synapse-memory ingest-audit --source codex --limit 50 --no-semantic-retrieval`
  provider 기반 관련 페이지 선별 호출을 제외한 저비용 모드의 예상 호출 수를 확인합니다.
- `synapse-memory backfill --source codex`
  빈 vault를 전체 raw 이력으로 1회 재구축 (배치, 중단해도 재개 가능). 대량 첫 구축용.
- `synapse-memory backfill --source codex --batch-size 5 --max-batches 1 --no-semantic-retrieval`
  관련 페이지 선별 호출을 끄고 작은 배치로 검증 실행합니다. 비용은 줄지만 기존 페이지
  갱신 대상을 덜 정확하게 고를 수 있습니다.
- `synapse-memory watch run`
  한 사이클에서 `claude-code`와 `codex` 두 소스를 모두 ingest. launchd가 20분마다 자동 실행.

watermark는 소스별로 분리 저장되며 마이크로초 정밀도 ISO 타임스탬프를 씁니다(파일은 mtime
순으로 처리, 이미 통합한 대화는 건너뜀). 동작 원리 요약은 README의 "파이프라인 동작 원리"를 보세요.

ingest 비용 정책은 문서 크기 기준으로 고정됩니다. 40,000자 이하는 관련 페이지 선별
1회와 전체 본문 통합 1회로 보통 2회 호출합니다. 40,000자를 넘고 120,000자 이하인
문서는 provider 기반 관련 페이지 선별을 끄고 앞/뒤/고신호 라인 샘플만 1회 통합합니다.
120,000자를 넘는 초대형 문서는 LLM 없이 skip하고 watermark를 전진시켜 backfill
queue가 같은 파일에서 멈추지 않게 합니다.

질문 경로(`ask`, `wiki ask`, `persona decide/recall/resume`)는 wiki 카드와 사용자가 승인한
Profile/DecisionPatterns를 중심으로 provider에 전달합니다. raw mirror를 provider에 보내는
경로는 wiki 통합용 ingest/backfill/watch입니다.

`--no-semantic-retrieval`을 쓰면 40,000자 이하 문서도 provider 기반 관련 페이지 선별을
생략합니다. 작은 문서는 보통 2회 호출에서 1회 호출로 줄지만, 제목/slug 이름 매칭과
1-hop 링크만으로 기존 페이지 갱신 대상을 찾습니다.

### raw mirror 수동 축소 — `compact-raw`

이미 ingest된 `claude-code`/`codex` raw mirror에서 provider 통합에 쓰지 않는 tool I/O
라인을 gzip sidecar로 분리합니다. 기본은 dry-run이라 파일을 바꾸지 않습니다.

```bash
synapse-memory compact-raw
synapse-memory compact-raw --source codex
synapse-memory compact-raw --apply --yes
synapse-memory compact-raw --rehydrate --apply --yes
```

`--apply`는 공유 `ingest.lock`을 기다린 뒤 실행합니다. watch/backfill/ingest가 돌고
있으면 먼저 끝나기를 기다리거나 해당 작업을 정상 종료한 뒤 실행하세요.

## 완전히 지우고 싶을 때

처리 데이터 삭제와 개인정보 경계는 [개인정보, 비용, 삭제](privacy-and-cost.md)를
따르세요. 문서나 초안을 지우기 전에는 Obsidian에서 필요한 내용이 없는지 먼저 확인합니다.
