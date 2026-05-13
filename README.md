# Synapse Memory

Synapse Memory는 내 Obsidian 노트와 Claude Code/Codex 작업 기록을 매일 정리해
필요할 때 다시 꺼내 쓰게 해주는 개인용 AI 메모리 도구입니다.

원본 자료는 내 Mac 안의 `~/.synapse/private/`에 머물고, 외부 AI에는 민감정보를
가린 요약 카드와 사용자가 승인한 자료만 전달합니다.

## 먼저 무엇을 해결하나요?

노트가 쌓이면 보통 세 가지가 먼저 불편해집니다.

1. 분명 적어둔 내용을 다시 찾기 어렵습니다.
2. 새 AI 대화마다 내 프로젝트 맥락을 처음부터 설명해야 합니다.
3. 이력서, 회고, 의사결정처럼 "내가 예전에 뭘 했고 어떻게 판단했는지"가 필요한 작업을 매번 다시 정리합니다.

Synapse Memory는 매일 새 노트와 대화 기록을 모으고, 회사/프로젝트 단위의 요약
카드를 만들고, 그 카드로 질문에 답합니다. 그래서 사용자는 원본 파일을 뒤지기보다
`/synapse-ask`, `/synapse-recall`, `/synapse-resume` 같은 짧은 명령으로 자기 자료를
다시 사용할 수 있습니다.

## 가장 짧은 시작 흐름

Claude Code 또는 Codex에서 다음 순서로 시작합니다.

```text
/synapse-doctor
/synapse-daily
/synapse-ask "내 iOS 프로젝트 구조를 요약해줘"
```

처음 실행하는 `daily`는 노트 양에 따라 오래 걸릴 수 있습니다. 빠르게 첫 답변을
보고 싶다면 터미널에서 quick 모드를 먼저 실행합니다.

```bash
synapse-memory daily --quick
```

그 뒤에는 `/synapse-assistant`를 부르면 현재 상태를 보고 오늘 할 일을 1-3개로
줄여서 제안합니다.

## 설치

설치는 세 가지 흐름이 있습니다. 처음이라면 **방법 A**를 권장합니다.

### 방법 A - AI에게 자동 설치 준비 맡기기

Claude Code 또는 Codex 채팅창에 아래 프롬프트를 그대로 붙여넣습니다. AI가 설치 zip을
받고, 압축을 풀고, 실행 전 검증까지 대신합니다. 실제 실행이나 보안 경고 우회처럼
사용자 승인이 필요한 단계에서는 멈추도록 설계한 프롬프트입니다.

```text
Synapse Memory를 설치해줘.

설치 파일은 아래 링크에서 받아줘.
https://github.com/Jimmy-Jung/synapse-memory/releases/download/v0.7.0/SynapseMemory-v0.7.0-macos-installer.zip

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

1. [SynapseMemory-v0.7.0-macos-installer.zip][installer-zip]을 다운로드합니다.
2. zip을 열고 `installer/SynapseMemory-Installer.command`를 실행합니다.
3. 안내에 따라 Obsidian vault를 선택하고 환경 점검을 마칩니다.
4. Claude Code 또는 Codex에서 `/synapse-doctor`로 상태를 확인합니다.

macOS 보안 경고가 나오면 파일을 우클릭한 뒤 "열기"를 선택합니다. 설치 프로그램은
기본적으로 preview 모드로 동작하며, 실제 변경이 필요한 단계에서는 사용자 확인을
받습니다.

### 방법 C - 플러그인만 직접 설치하기

이미 `synapse-memory` CLI와 runtime이 준비되어 있고 Claude Code/Codex 플러그인만
붙이고 싶을 때 사용합니다.

Claude Code:

```bash
claude plugin marketplace add --scope user Jimmy-Jung/synapse-memory
claude plugin install --scope user synapse-memory@synapse-memory-marketplace
claude plugin enable --scope user synapse-memory@synapse-memory-marketplace
claude plugin list
```

`claude plugin list`에서 `synapse-memory@synapse-memory-marketplace`가 enabled로
보이면 설치된 상태입니다.

Codex:

```bash
codex plugin marketplace add Jimmy-Jung/synapse-memory
```

그 다음 `~/.codex/config.toml`에 플러그인이 활성화되어 있어야 합니다.

```toml
[plugins."synapse-memory@synapse-memory-marketplace"]
enabled = true
```

확인은 다음처럼 합니다.

```bash
codex debug prompt-input "Synapse Memory plugin visibility check" \
  | grep "synapse-memory:synapse-memory"
```

출력이 있으면 Codex가 Synapse Memory skill을 볼 수 있는 상태입니다.

## 매일 쓰는 명령

| 하고 싶은 일 | 명령 |
| --- | --- |
| 환경 점검 | `/synapse-doctor` |
| 자동 복구 가능한 문제 수정 | `/synapse-fix` |
| 새 노트와 대화 기록 정리 | `/synapse-daily` |
| 내 자료에 질문 | `/synapse-ask "질문"` |
| 예전에 한 생각 회상 | `/synapse-recall "주제"` |
| 의사결정 도움 받기 | `/synapse-decide "상황"` |
| 회사 맞춤 이력서 초안 | `/synapse-resume <회사>` |
| 오늘 할 일 추천 | `/synapse-assistant` |

터미널에서 직접 실행할 때는 같은 기능을 `synapse-memory` CLI로 사용할 수 있습니다.

```bash
synapse-memory doctor
synapse-memory daily --quick
synapse-memory ask "TCA를 왜 도입했지?"
synapse-memory persona what-did-i-think "AI 코딩 도구"
synapse-memory persona draft-resume examplecorp
```

## 문서 읽는 순서

문서는 네 장만 보면 됩니다.

1. [문서 안내](docs/README.md) - 전체 흐름
2. [처음부터 끝까지 사용하기](docs/start-here.md) - 설치 후 첫 질문까지
3. [개인정보, 비용, 삭제](docs/privacy-and-cost.md) - 안전 경계와 운영 비용
4. [명령과 문제 해결](docs/reference.md) - 자주 쓰는 명령, 설정, 복구

## 요구사항

- Apple Silicon Mac
- macOS Tahoe 26.0 이상
- Obsidian vault
- Claude Code 또는 Codex
- 로컬 AI 도구 `apfel`

Intel Mac과 macOS 25 이하는 현재 지원하지 않습니다.

## 라이선스

MIT - [LICENSE](LICENSE)

[installer-zip]: https://github.com/Jimmy-Jung/synapse-memory/releases/download/v0.7.0/SynapseMemory-v0.7.0-macos-installer.zip
