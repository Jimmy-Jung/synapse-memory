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
codex debug prompt-input \
  --disable apps --disable memories --disable chronicle --disable multi_agent \
  "Synapse Memory plugin visibility check" \
  | grep "sm:doctor"
```

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

quick과 full을 동시에 실행하지 마세요. 둘 다 같은 로컬 색인을 갱신하므로 한 번에 하나만
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

## 완전히 지우고 싶을 때

처리 데이터 삭제와 개인정보 경계는 [개인정보, 비용, 삭제](privacy-and-cost.md)를
따르세요. 문서나 초안을 지우기 전에는 Obsidian에서 필요한 내용이 없는지 먼저 확인합니다.
