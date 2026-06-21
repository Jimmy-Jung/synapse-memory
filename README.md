# Synapse Memory

Synapse Memory는 Claude Code/Codex 등 어떤 AI 툴과의 대화든 자동으로 인식해
서로 연결된 Obsidian wiki로 자동 구축·유지해 주는 개인용 AI 메모리 도구입니다.
이제는 매일 수동으로 정리를 돌릴 필요 없이, 대화가 쌓이는 대로 wiki가 알아서
정리됩니다.

대화 원본은 내 Mac 안의 `~/.synapse/private/`에 미러로 로컬 보관됩니다.

## 먼저 무엇을 해결하나요?

노트가 쌓이면 보통 세 가지가 먼저 불편해집니다.

1. 분명 적어둔 내용을 다시 찾기 어렵습니다.
2. 새 AI 대화마다 내 프로젝트 맥락을 처음부터 설명해야 합니다.
3. 이력서, 회고, 의사결정처럼 "내가 예전에 뭘 했고 어떻게 판단했는지"가 필요한 작업을 매번 다시 정리합니다.

Synapse Memory는 새 노트와 대화 기록을 자동으로 모아 서로 연결된 wiki와 회사/
프로젝트 단위의 요약 카드로 정리하고, 그 wiki로 질문에 답합니다. 그래서 사용자는 원본 파일을 뒤지기보다
Claude Code에서는 `/sm:ask`, `/sm:recall`, `/sm:resume` 같은 짧은 명령으로,
Codex에서는 `$ask`, `$recall`, `$resume` 같은 skill 호출로 자기 자료를 다시 사용할
수 있습니다.

## 가장 짧은 시작 흐름

Claude Code에서는 다음 순서로 시작합니다.

```text
/sm:doctor
/sm:daily
/sm:ask "내 iOS 프로젝트 구조를 요약해줘"
```

Codex TUI에서는 `/sm`이 아니라 `$`로 skill을 검색합니다.

```text
$doctor
$daily
$ask "내 iOS 프로젝트 구조를 요약해줘"
```

처음 실행하는 `daily`는 노트 양에 따라 오래 걸릴 수 있습니다. 빠르게 첫 답변을
보고 싶다면 터미널에서 quick 모드를 먼저 실행합니다.

```bash
synapse-memory daily --quick
```

그 뒤에는 Claude Code에서 `/sm:assistant`, Codex에서 `$assistant`를 실행하면 현재
상태를 보고 오늘 할 일을 1-3개로 줄여서 제안합니다.

## 설치

설치는 세 가지 흐름이 있습니다. 처음이라면 **방법 A**를 권장합니다.

### 방법 A - AI에게 자동 설치 준비 맡기기

Claude Code 또는 Codex 채팅창에 아래 프롬프트를 그대로 붙여넣습니다. AI가 설치 zip을
받고, 압축을 풀고, 실행 전 검증까지 대신합니다. 실제 실행이나 보안 경고 우회처럼
사용자 승인이 필요한 단계에서는 멈추도록 설계한 프롬프트입니다.

```text
Synapse Memory를 설치해줘.

설치 파일은 아래 링크에서 받아줘.
https://github.com/Jimmy-Jung/synapse-memory/releases/download/v1.18.1/SynapseMemory-v1.18.1-macos-installer.zip

다운로드한 zip을 압축 해제한 뒤
installer/SynapseMemory-Installer.command가 있는지 확인하고,
zsh -n으로 문법 검사까지 해줘.

그 다음에는 바로 실행하지 말고 멈춘 뒤,
내가 직접 실행할 수 있는 방법을 안내해줘.

내가 "실행해"라고 명시적으로 말하면 기본 preview 모드로 실행해줘.
내가 "실제 적용해"라고 명시적으로 말하기 전까지는
SYNAPSE_INSTALLER_DRY_RUN=0을 붙이지 마.

설치 중 macOS 보안 경고가 뜨면 임의로 보안 설정을 바꾸지 말고,
내가 직접 열 수 있도록 안내해줘.

GUI 동의, Obsidian 저장소 위치 선택, Gatekeeper 우회, 실제 적용처럼
내가 직접 승인해야 하는 단계에서는 멈추고 안내해줘.

내가 설치를 실행했다고 알려주면,
최신 로그 경로와 synapse-memory doctor 결과를 확인해서 요약해줘.
```

### 방법 B - 직접 다운로드해서 실행하기

1. [SynapseMemory-v1.18.1-macos-installer.zip][installer-zip]을 다운로드합니다.
2. zip을 열고 `installer/SynapseMemory-Installer.command`를 실행합니다.
3. 안내에 따라 Obsidian vault를 선택하고 환경 점검을 마칩니다.
4. Claude Code에서는 `/sm:doctor`, Codex에서는 `$doctor`로 상태를 확인합니다.

macOS 보안 경고가 나오면 파일을 우클릭한 뒤 "열기"를 선택합니다. 설치 프로그램은
기본적으로 preview 모드로 동작하며, 실제 변경이 필요한 단계에서는 사용자 확인을
받습니다.

### 방법 C - 플러그인만 직접 설치하기

이미 `synapse-memory` CLI와 runtime이 준비되어 있고 Claude Code/Codex 플러그인만
붙이고 싶을 때 사용합니다.

Claude Code:

```bash
claude plugin marketplace add --scope user Jimmy-Jung/synapse-memory
claude plugin install --scope user sm@synapse-memory-marketplace
claude plugin enable --scope user sm@synapse-memory-marketplace
claude plugin list
```

`claude plugin list`에서 `sm@synapse-memory-marketplace`가 enabled로
보이면 설치된 상태입니다. 슬래시 명령은 `/sm:ask`, `/sm:daily`처럼 짧은 prefix로 노출됩니다.

Codex:

```bash
codex plugin marketplace add Jimmy-Jung/synapse-memory
codex plugin marketplace upgrade synapse-memory-marketplace
```

Codex CLI에서는 marketplace snapshot을 갱신한 뒤 plugin catalog와 config를 확인합니다.
플러그인 이름은 `synapse-memory`가 아니라 manifest 이름인 `sm`입니다.

```toml
[plugins."sm@synapse-memory-marketplace"]
enabled = true
```

확인은 다음처럼 합니다.

```bash
codex plugin list | grep 'sm@synapse-memory-marketplace'
codex debug prompt-input \
  --disable apps --disable memories --disable chronicle --disable multi_agent \
  "Synapse Memory plugin visibility check" \
  | grep "synapse-memory-marketplace/sm"
```

출력이 있으면 Codex가 Synapse Memory plugin skill root를 볼 수 있는 상태입니다. Codex TUI의
Plugins 브라우저에는 custom git marketplace가 표시되지 않을 수 있습니다. 이 경우에도
`$ask`처럼 `$`로 skill을 검색했을 때 `ask (sm)`가 보이면 사용할 수 있습니다.
plugin update 직후 기존 Codex 세션에는 이전 skill 목록이 남을 수 있으므로 새 세션에서
확인합니다.
Codex marketplace catalog는 `.agents/plugins/marketplace.json`에 있고,
Codex install source는 `plugins/sm/.codex-plugin/plugin.json`입니다.

## 매일 쓰는 명령

| 하고 싶은 일 | Claude Code | Codex | 터미널 |
| --- | --- | --- | --- |
| 환경 점검 | `/sm:doctor` | `$doctor` | `synapse-memory doctor` |
| 자동 복구 가능한 문제 수정 | `/sm:fix` | `$fix` | `synapse-memory doctor --fix` |
| 새 노트와 대화 기록 정리 | `/sm:daily` | `$daily` | `synapse-memory daily --quick` |
| 내 자료에 질문 | `/sm:ask "질문"` | `$ask "질문"` | `synapse-memory ask "질문"` |
| 예전에 한 생각 회상 | `/sm:recall "주제"` | `$recall "주제"` | `synapse-memory persona what-did-i-think "주제"` |
| 의사결정 도움 받기 | `/sm:decide "상황"` | `$decide "상황"` | `synapse-memory persona decide "상황"` |
| 회사 맞춤 이력서 초안 | `/sm:resume <회사>` | `$resume <회사>` | `synapse-memory persona draft-resume <회사>` |
| 오늘 할 일 추천 | `/sm:assistant` | `$assistant` | `synapse-memory assistant-status` |

### v0.9.0+ 추가 명령

| 하고 싶은 일 | Claude Code | Codex | 터미널 |
| --- | --- | --- | --- |
| Profile 후보 항목별 GUI 승인 | `/sm:apply-profile [date]` | `$apply-profile` | `synapse-memory list-pending-profiles` (보조) |
| 다른 프로젝트에 sm 컨텍스트 marker 삽입 | `/sm:setup` | `$setup` | `synapse-memory setup` |
| 등록된 프로젝트 marker + hook 캐시 갱신 | `/sm:sync` | `$sync` | `synapse-memory sync` |
| MOC.md 생성·갱신 (Obsidian Graph 진입점) | `/sm:moc` | `$moc` | `synapse-memory moc` |
| MemoryInbox / DailyReports flat → year/month 1회 마이그레이션 | — | — | `synapse-memory migrate-folders` |

### v1.16.x 추가 명령

| 하고 싶은 일 | Claude Code | Codex | 터미널 |
| --- | --- | --- | --- |
| 답변을 Insight 카드로 저장 (지식 축적) | `/sm:ask "질문" --save` | `$ask "질문" --save` | `synapse-memory ask "질문" --save` |
| Claude Code/Codex 세션 자동 컨텍스트 주입 hook 설치 | — | — | `synapse-memory hook install` |
| hook 컨텍스트 캐시 수동 갱신 | — | — | `synapse-memory context render` |
| marker 파일 없이 프로젝트 등록 (hook 전용) | — | — | `synapse-memory setup --no-marker` |

`ask --save`로 저장한 답변은 `<vault>/20_Reference/Insights/`에 카드로 쌓이고
다음 질문의 검색 대상이 됩니다. 좋은 답변이 채팅에서 증발하지 않고 누적됩니다.

### v1.17.0 추가 — 자동 wiki 엔진

v1.17.0부터는 AI 대화가 자동으로 인식되어 wiki로 통합·유지됩니다. 대부분은
`watch install` 한 번이면 끝나고, 아래 명령은 수동 제어가 필요할 때 사용합니다.

| 하고 싶은 일 | 터미널 |
| --- | --- |
| 자동 트리거 설치 — 이후 대화가 wiki에 자동 통합 (launchd) | `synapse-memory watch install` |
| 자동 트리거 상태 확인 / 제거 | `synapse-memory watch status` / `synapse-memory watch uninstall` |
| watch 작업을 지금 한 번 직접 실행 | `synapse-memory watch run` |
| 쌓인 raw 대화를 지금 wiki로 통합 | `synapse-memory ingest --now` |
| wiki 구조 자동수정 + 검토 큐 갱신 | `synapse-memory lint --now` |
| 전체 대화 이력을 wiki로 1회 구축 | `synapse-memory backfill` |
| wiki 근거로 질문에 답변 (인용 포함) | `synapse-memory wiki ask "<질문>"` |

`watch install`로 한 번 설치하면 이후 Claude/Codex 대화가 자동으로 wiki에
통합되므로, 보통은 `ingest`/`lint`를 직접 돌릴 필요가 없습니다. 처음 도입할 때
기존 이력을 한 번에 정리하려면 `backfill`을 먼저 실행하세요.

신규 명령 자세한 사용법은 [docs/reference.md](docs/reference.md)를 참고하세요.

#### 파이프라인 동작 원리 (collect → ingest → watch)

대화가 wiki가 되기까지 3단계를 거칩니다. 핵심은 **느린 LLM 단계(ingest)와 빠른
복사 단계(collect)의 분리**, 그리고 **이미 처리한 대화는 다시 보지 않는 watermark**입니다.

```
[AI 로그]                [L0 raw 미러]                  [Obsidian vault]
~/.claude  ──collect──▶  ~/.synapse/private/raw  ──ingest(LLM)──▶  wiki 페이지
~/.codex                 (jsonl 그대로 복사)          (대화→페이지 통합)
```

| 단계 | 하는 일 | LLM 호출 | 속도 |
| --- | --- | --- | --- |
| **collect** | AI 로그(jsonl)를 raw로 증분 복사 (`collect claude-code` / `collect codex`) | ✗ | 빠름 (파일 I/O) |
| **ingest** | raw 대화 1건씩 LLM에 읽혀 관련 wiki 페이지에 통합 (`ingest --source …`) | ✓ 대화당 1회 | 느림 |
| **watch** | launchd가 **20분마다** 위 두 단계를 자동 실행 (`watch install`) | ✓ | 백그라운드 |

- **doc = 대화 세션 파일 1개.** ingest는 doc 하나를 LLM에 통째로 읽혀 페이지를 만들거나 갱신합니다.
- **privacy mode.** collect/mirror는 로컬 private 폴더에만 복사합니다. ingest/backfill/watch는
  wiki 통합을 위해 small raw 전체 또는 sampled raw 일부를 provider로 보낼 수 있고,
  ask/query 경로는 wiki 카드와 승인된 Profile/DecisionPatterns를 중심으로 보냅니다.
- **소스(source)와 LLM은 별개.** `--source`는 *어느 도구의 로그*(claude-code / codex)를
  읽을지 고를 뿐이고, 통합에 쓰는 LLM은 `~/.synapse/config.yaml`의 `ai_provider`가 정합니다.
  두 소스 모두 같은 provider가 처리합니다.
- **watermark로 재처리 방지.** 소스별로 마지막 처리 시각을 기록해, 이미 통합한 대화는
  건너뛰고 새 대화만 LLM에 보냅니다. 진행 중(최근 수정) 세션은 settled 필터로 잠시 대기합니다.
- **watch는 상시 데몬이 아닙니다.** 20분마다 짧게 돌고 끝나며, 평소엔 프로세스가 없습니다.

#### 최초 설치 후 사용 흐름

```bash
# 1) 자동 컨텍스트 주입 hook (전역 1회)
synapse-memory hook install

# 2) 자동 통합 데몬 설치 — 이후 대화가 20분마다 wiki로 자동 통합
synapse-memory watch install

# 3) (선택) 기존 대화 이력 한 번에 구축 — 소스별로
synapse-memory backfill --source claude-code
synapse-memory backfill --source codex

# 4) 정상 동작 점검
synapse-memory doctor
synapse-memory watch status      # 설치 여부 + 소스별 watermark
```

설치 후에는 손댈 게 없습니다. 대화를 하면 세션 종료 시 raw로 미러되고, watch가 20분마다
wiki로 통합합니다. `backfill`은 **대량 첫 구축**용으로, 끊겨도 다시 실행하면 이어서 처리합니다.
진행 상황은 `~/.synapse/private/watch.out.log`(통합 결과)와 `watch.err.log`(에러)에서 봅니다.

터미널에서 직접 실행할 때는 같은 기능을 `synapse-memory` CLI로 사용할 수 있습니다.

```bash
synapse-memory doctor
synapse-memory daily --quick
synapse-memory ask "TCA를 왜 도입했지?"
synapse-memory persona what-did-i-think "AI 코딩 도구"
synapse-memory persona draft-resume examplecorp
```

## 자동 컨텍스트 주입 (hook)

매번 `/sm:setup`으로 marker를 관리하지 않아도, 전역 hook 한 번 설치로 등록된
프로젝트에서 Claude Code/Codex 세션 시작 시 Profile/DecisionPatterns 요약이 자동 주입됩니다.

```bash
synapse-memory hook install        # 전역 1회
synapse-memory setup --no-marker   # 프로젝트마다 — repo 파일 수정 없이 등록
```

- Profile 승인(`/sm:apply-profile`) 후 컨텍스트 캐시가 자동 갱신되어 다음
  세션부터 바로 반영됩니다. 수동 갱신은 `synapse-memory context render`.
- 개인 Profile 내용이 git에 커밋되는 `CLAUDE.md`에 남지 않습니다.
- Codex는 첫 hook 실행 전 `/hooks`에서 설치된 command hook을 신뢰 승인해야 할 수 있습니다.
- hook을 쓰지 않는 프로젝트는 기존처럼 `synapse-memory setup --target codex`로
  `AGENTS.md` marker를 사용할 수 있습니다. `/sm:sync`는 marker 갱신 + 캐시 재렌더를
  함께 수행합니다.
- 설치 상태는 `synapse-memory doctor`가 점검합니다.

## 문서 읽는 순서

문서는 네 장만 보면 됩니다.

1. [문서 안내](docs/README.md) - 전체 흐름
2. [처음부터 끝까지 사용하기](docs/start-here.md) - 설치 후 첫 질문까지
3. [개인정보, 비용, 삭제](docs/privacy-and-cost.md) - 데이터 보관 위치와 운영 비용
4. [명령과 문제 해결](docs/reference.md) - 자주 쓰는 명령, 설정, 복구

## 요구사항

- macOS (launchd 기반 자동 통합 데몬)
- Obsidian vault
- Claude Code 또는 Codex (통합에 쓰는 LLM provider 제공)

로컬 LLM/임베딩을 쓰지 않으므로 GPU·대용량 메모리나 특정 칩셋/macOS 버전 요구사항은 없습니다.

## 라이선스

MIT - [LICENSE](LICENSE)

[installer-zip]: https://github.com/Jimmy-Jung/synapse-memory/releases/download/v1.18.1/SynapseMemory-v1.18.1-macos-installer.zip
