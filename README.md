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

가장 쉬운 방법은 Release zip을 받은 뒤 installer를 실행하는 것입니다.

1. [SynapseMemory-v0.7.0-macos-installer.zip][installer-zip]을 다운로드합니다.
2. zip을 열고 `installer/SynapseMemory-Installer.command`를 실행합니다.
3. 안내에 따라 Obsidian vault를 선택하고 환경 점검을 마칩니다.
4. Claude Code 또는 Codex에서 `/synapse-doctor`로 상태를 확인합니다.

macOS 보안 경고가 나오면 파일을 우클릭한 뒤 "열기"를 선택합니다. 설치 프로그램은
기본적으로 preview 모드로 동작하며, 실제 변경이 필요한 단계에서는 사용자 확인을
받습니다.

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
