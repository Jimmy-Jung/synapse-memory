# 개인정보, 비용, 삭제

작성자: JunyoungJung  
작성일: 2026-05-13

Synapse Memory는 개인 자료를 다루므로 기능보다 안전 경계가 먼저입니다. 이 문서는
무엇이 내 Mac 안에 남고, 무엇이 외부 AI로 나가며, 비용이 언제 발생하는지 설명합니다.

## 원본은 어디에 있나요?

원본 mirror와 처리 중간 파일은 `~/.synapse/private/` 아래에 저장됩니다. 이 폴더는
내 Mac 안의 로컬 저장소이며, 권한은 다른 사용자가 쉽게 볼 수 없도록 제한하는 것을
전제로 합니다.

Obsidian vault에는 사용자가 읽고 검토할 수 있는 결과물이 남습니다.

| 자료 | 저장 위치 | 외부 AI 전송 여부 |
| --- | --- | --- |
| 원본 노트 mirror | `~/.synapse/private/` | 전송하지 않음 |
| Claude/Codex 작업 기록 mirror | `~/.synapse/private/` | 전송하지 않음 |
| 마스킹된 사본 | `~/.synapse/private/` | 필요한 경우에만 사용 |
| 프로젝트/회사 요약 카드 | Obsidian vault | 질문에 필요한 카드만 전송 |
| Profile/DecisionPatterns | Obsidian vault | 사용자가 승인한 내용만 전송 |

## 외부 AI에는 무엇이 나가나요?

외부 AI에는 질문에 필요한 최소 자료만 전달합니다.

1. 관련 요약 카드
2. 민감정보를 가린 텍스트
3. 사용자가 직접 승인한 Profile/DecisionPatterns

이메일, 전화번호, 계좌번호, 토큰, 주민번호처럼 패턴이 분명한 값은 정규식 기반으로
먼저 가립니다. 사람 이름, 조직명, 주소처럼 문맥이 필요한 값은 로컬 AI 도구가 한 번 더
확인하는 구조를 사용합니다.

특정 회사명이나 프로젝트명을 절대 보내고 싶다면 redact-list에 추가합니다.

```bash
synapse-memory redactlist add "회사명"
```

## AI가 마음대로 내 성향을 확정하나요?

아니요. `daily`와 `persona ingest`는 Profile 후보를 `MemoryInbox`에 만들 뿐입니다.
사용자가 Obsidian에서 검토하고 `Profile.md`나 `DecisionPatterns.md`로 옮긴 내용만
승인된 자료로 사용합니다.

이 흐름은 불편해 보일 수 있지만, 개인 메모리 도구에서는 중요한 안전 장치입니다.
AI가 잘못 추측한 내용을 곧바로 "나의 성향"으로 쓰지 않게 막습니다.

## 비용은 언제 발생하나요?

비용은 외부 AI를 호출할 때 발생합니다. 로컬 파일 이동, 진단, 설정 확인, cleanup scan
같은 작업은 별도 AI 비용이 들지 않습니다.

| 작업 | 비용 감각 |
| --- | --- |
| 환경 점검 (`/sm:doctor`, `$doctor`, `synapse-memory doctor`) | 무료에 가까움 |
| 자동 복구 확인 (`/sm:fix`, `$fix`, `synapse-memory doctor --fix`) | 대부분 로컬 작업 |
| `synapse-memory daily --quick` | 적은 비용, 첫 체험용 |
| `synapse-memory daily` | 노트 양에 따라 비용과 시간이 커질 수 있음 |
| 질문하기 (`/sm:ask`, `$ask`, `synapse-memory ask`) | 질문마다 외부 AI 호출 가능 |
| 이력서 초안 (`/sm:resume`, `$resume`) | 이력서 초안 생성 시 외부 AI 호출 |
| 의사결정 도움 (`/sm:decide`, `$decide`) | 상황 판단 시 외부 AI 호출 |

최근 비용은 다음 명령으로 확인합니다.

```bash
synapse-memory cost summary --days 30 --by command
```

## 비용을 줄이는 방법

- 첫 실행은 `synapse-memory daily --quick`으로 시작합니다.
- 매일은 quick, 주 1회만 full `daily`를 실행합니다.
- 같은 질문을 반복하기 전에 카드와 Profile 후보를 먼저 검토합니다.
- 불필요한 draft와 오래된 MemoryInbox 후보는 Claude Code `/sm:cleanup`, Codex
  `$cleanup`, 또는 `synapse-memory cleanup scan`으로 정리 후보를 확인합니다.

## 노트북을 잃어버리면 어떻게 되나요?

Obsidian vault를 iCloud 등으로 동기화했다면 요약 카드와 사용자가 승인한 Profile 자료는
복구할 수 있습니다. `~/.synapse/private/`의 처리 데이터는 새 Mac에서 다시 만들 수
있습니다.

단, private 폴더 안에는 원본 mirror와 처리 중간 파일이 있으므로 Mac 자체의 디스크 암호화,
계정 잠금, 백업 정책을 함께 관리해야 합니다.

## 완전히 삭제하려면

Synapse Memory가 만든 로컬 처리 데이터를 지웁니다.

```bash
rm -rf ~/.synapse
```

글로벌 CLI로 설치했다면 제거합니다.

```bash
python3 -m pip uninstall synapse-memory
```

Homebrew로 설치한 로컬 AI 도구가 필요 없다면 제거합니다.

```bash
brew uninstall apfel
```

Obsidian vault 안의 요약 카드와 초안은 사용자가 직접 지웁니다.

```text
20_Reference/Projects/
20_Reference/Companies/
30_Creative/Drafts/
90_System/AI/
```

삭제 전에는 필요한 카드와 초안이 없는지 Obsidian에서 먼저 확인하세요.
