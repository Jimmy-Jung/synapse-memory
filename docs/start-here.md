# 처음부터 끝까지 사용하기

작성자: JunyoungJung  
작성일: 2026-05-13

Synapse Memory는 "내 자료를 AI가 다시 쓸 수 있게 정리하는 도구"입니다. 시작은
거창하지 않습니다. Obsidian vault 하나를 고르고, 새 노트와 Claude Code/Codex 작업
기록을 모으고, 필요한 순간에 질문하면 됩니다.

## 1. 왜 필요한가요?

노트와 AI 대화는 계속 쌓이지만, 다시 쓰기는 어렵습니다.

- 정확한 파일명이나 키워드가 기억나지 않습니다.
- 새 AI 대화를 열 때마다 프로젝트 배경을 다시 설명합니다.
- 이력서, 회고, 의사결정처럼 "내가 예전에 무엇을 했는지"가 필요한 작업을 매번 다시 정리합니다.

Synapse Memory는 이 흐름을 매일 조금씩 정리합니다. 원본은 먼저 내 Mac의
`~/.synapse/private/`에 mirror합니다. 이후 `ingest`/`backfill`/`watch`가 wiki로 통합할
때는 small raw 대화 전체 또는 sampled raw 일부가 설정된 provider로 갈 수 있고,
`ask`/`persona` 같은 질문 경로는 wiki 카드와 사용자가 승인한 Profile/DecisionPatterns를
중심으로 보냅니다.

## 2. 어떤 데이터를 수집하나요?

v1.17+ 기준으로 다음 소스를 자동으로 mirror합니다. mirror/collect 단계에서는 모두
`~/.synapse/private/`(0700) 안에 저장되고 외부 AI 호출은 없습니다. 이후
ingest/backfill/watch 단계에서는 wiki 통합을 위해 small raw 또는 sampled raw가 provider로
전송될 수 있습니다.

| 분류 | 소스 | 활성화 |
| --- | --- | --- |
| AI 활동 | Claude Code 세션, Codex CLI 세션 | 자동 |
| 개발 환경 | shell history, Cursor IDE, Continue.dev, Aider, VS Code Local History | 자동 |
| 메모 / 일기 | Obsidian vault, Apple Notes, Day One | 자동 |
| macOS 시스템 | Calendar, 브라우저(Chrome/Safari/Arc) history, Screen Time | 자동 |
| PII 민감 (선택) | iMessage `chat.db` | Full Disk Access 부여 시 |
| 외부 서비스 (선택) | Gmail Sent | `SYNAPSE_GMAIL_ENABLE=1` + OAuth |
| 본인 활동 (선택) | 본인 git commit | `SYNAPSE_GIT_SELF_ROOTS=...` 지정 시 |
| 건강 (선택) | iOS Health export | `~/Downloads/export*.zip` 드롭 시 |

각 소스가 존재하지 않거나 권한이 없으면 자동 skip — 실패 아닙니다. 상세 권한 절차 +
opt-out 방법은 [명령과 문제 해결](reference.md) "외부 데이터 수집기" 섹션 참고.

## 3. 처음 실행

Claude Code에서는 아래 순서로 실행합니다.

```text
/sm:doctor
/sm:daily
/sm:ask "내 최근 프로젝트를 요약해줘"
```

Codex TUI에서는 `/`가 아니라 `$`로 skill을 검색합니다.

```text
$doctor
$daily
$ask "내 최근 프로젝트를 요약해줘"
```

각 명령의 역할은 단순합니다.

| 기능 | Claude Code | Codex |
| --- | --- | --- |
| 환경 점검 | `/sm:doctor` | `$doctor` |
| 새 자료 정리 | `/sm:daily` | `$daily` |
| Profile 후보 GUI 승인 | `/sm:apply-profile` | `$apply-profile` |
| 자료에 질문 | `/sm:ask` | `$ask` |

첫 `daily`는 노트 양에 따라 오래 걸릴 수 있습니다. 빠르게 체험하려면 터미널에서
quick 모드를 먼저 실행합니다.

```bash
synapse-memory daily --quick
```

quick 모드는 최근 변경분만 처리하므로 첫 답변까지 가는 시간이 짧습니다. 이후 주 1회
정도는 전체 `daily`를 실행해 Profile 후보와 누락된 카드를 정리하는 흐름을 권장합니다.

## 4. 결과는 어디에 남나요?

크게 두 곳을 사용합니다.

| 위치 | 의미 |
| --- | --- |
| `~/.synapse/private/` | 원본 mirror, 처리 중간 파일, 로컬 색인. 내 Mac 안에만 둡니다. |
| Obsidian vault | 사용자가 읽고 검토할 수 있는 요약 카드, 초안, Profile 후보를 둡니다. |

Obsidian vault 안에서는 보통 다음 폴더를 씁니다.

| 폴더 | 역할 |
| --- | --- |
| `00_Inbox/` | 아직 정리하지 않은 새 메모 |
| `10_Active/<회사>/<프로젝트>/` | 진행 중인 프로젝트 노트 |
| `20_Reference/Projects/` | Synapse가 만든 프로젝트 요약 카드 |
| `20_Reference/Companies/` | Synapse가 만든 회사 요약 카드 |
| `30_Creative/Drafts/` | 이력서, 설계 초안 같은 생성물 |
| `90_System/AI/` | Profile, MemoryInbox, DailyReports 같은 시스템 자료 |

처음에는 모든 폴더를 완벽히 맞출 필요가 없습니다. `10_Active/<회사>/<프로젝트>/`에
프로젝트 노트를 모아두면 카드가 가장 잘 만들어집니다.

## 5. 매일 하는 일

매일 직접 모든 명령을 기억할 필요는 없습니다.

```text
/sm:assistant
```

Codex에서는 `$assistant`를 실행합니다. 이 기능은 현재 상태를 읽고 오늘 필요한 일을
줄여서 보여줍니다. 예를 들면 다음과 같습니다.

```text
환경: 정상
마지막 daily: 14시간 전
MemoryInbox 검토 대기: 4개
draft 카드: 3개

오늘 추천 작업:
1. MemoryInbox 4건 검토
2. daily 실행
3. draft 카드 3건 확인
```

사용자는 번호를 고르거나 직접 지시하면 됩니다.

## 6. 자료에 질문하기

가장 자주 쓰는 기능은 `ask`입니다. Claude Code에서는 slash 명령을 씁니다.

```text
/sm:ask "TCA를 왜 도입했지?"
/sm:ask "최근 이력서에 넣을 만한 iOS 성과를 찾아줘"
/sm:ask "이 프로젝트의 인증 구조를 요약해줘"
```

Codex에서는 `$ask`를 씁니다.

```text
$ask "TCA를 왜 도입했지?"
$ask "최근 이력서에 넣을 만한 iOS 성과를 찾아줘"
```

Synapse Memory는 질문과 비슷한 요약 카드를 찾고, 그 카드만 외부 AI에 보내 답을
받습니다. 원본 노트 전체를 보내지 않습니다.

## 7. 과거 생각을 회상하기

"내가 예전에 이 주제에 대해 뭐라고 했지?"에 가까운 질문은 recall을 씁니다.

```text
/sm:recall "AI 코딩 도구"
/sm:recall "모듈화 리팩터링"
```

Codex에서는 `$recall "AI 코딩 도구"`처럼 실행합니다.

터미널에서는 다음과 같습니다.

```bash
synapse-memory persona what-did-i-think "AI 코딩 도구"
```

자료가 충분하면 시간순 변화와 근거 카드를 함께 보여주고, 자료가 부족하면 부족하다고
말하도록 설계되어 있습니다.

## 8. 이력서와 의사결정

회사 맞춤 이력서 초안:

```text
/sm:resume examplecorp
```

Codex에서는 `$resume examplecorp`처럼 실행합니다.

의사결정 도움:

```text
/sm:decide "이번 PR을 하나로 낼까 기능 단위로 나눌까?"
```

Codex에서는 `$decide "이번 PR을 하나로 낼까 기능 단위로 나눌까?"`처럼 실행합니다.

이 두 기능은 `90_System/AI/Profile.md`와 `DecisionPatterns.md`가 채워질수록 좋아집니다.
Profile 후보는 `daily`가 `MemoryInbox`에 만들고, 사용자가 Obsidian에서 검토한 뒤
맞는 것만 직접 옮깁니다. AI가 추측한 내용을 승인 없이 곧바로 "나"로 확정하지 않는
것이 핵심입니다.

## 9. 외부 자료를 더하고 싶을 때

회고록, 일기, 자기소개서 초안처럼 vault 밖의 `.md` 또는 `.txt` 파일도 Profile 후보로
흡수할 수 있습니다.

```bash
synapse-memory persona ingest --file ~/Documents/retro-2026.md
```

원본 파일은 private 영역에 mirror되고, vault에는 검토용 후보만 생깁니다. PDF와 docx는
현재 지원하지 않습니다.

## 10. 문제가 생기면

먼저 진단합니다.

```text
/sm:doctor
```

Codex에서는 `$doctor`를 실행합니다.

자동으로 고칠 수 있는 문제는 다음 명령을 씁니다.

```text
/sm:fix
```

Codex에서는 `$fix`를 실행합니다.

직접 확인해야 할 때는 [명령과 문제 해결](reference.md)을 봅니다.
