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

중요한 구분이 하나 있습니다. **mirror/collect 단계**는 원본을 로컬 private 폴더에
복사만 하므로 외부 AI를 호출하지 않습니다. 반면 **ingest/backfill/watch 단계**는 raw
대화를 wiki 페이지로 통합하기 위해 설정된 provider(Claude 또는 Codex)에 small raw 문서
전체 또는 sampled raw 일부를 보낼 수 있습니다.

| 자료 | 저장 위치 | 외부 AI 전송 여부 |
| --- | --- | --- |
| Obsidian vault 노트 mirror | `~/.synapse/private/` | 전송하지 않음 |
| Claude/Codex 작업 기록 mirror | `~/.synapse/private/` | mirror 자체는 전송하지 않음. ingest/backfill/watch에서 small raw 또는 sampled raw 전송 가능 |
| 개발 환경 활동 mirror (Cursor / Continue / Aider) | `~/.synapse/private/` | 전송하지 않음 |
| 개인 일기 mirror (Day One) | `~/.synapse/private/` | 전송하지 않음 |
| Gmail Sent mirror (opt-in 시) | `~/.synapse/private/` | 전송하지 않음 |
| 프로젝트/회사 요약 카드 | Obsidian vault | 질문에 필요한 카드만 전송 |
| Profile/DecisionPatterns | Obsidian vault | 사용자가 승인한 내용만 전송 |

## 외부 AI에는 무엇이 나가나요?

외부 AI에 나가는 자료는 명령 경로에 따라 다릅니다.

`ask`, `wiki ask`, `persona decide/recall/resume` 같은 질문 경로는 질문에 필요한 최소
자료만 전달합니다.

1. 관련 요약 카드
2. 사용자가 직접 승인한 Profile/DecisionPatterns

`ingest`, `backfill`, `watch`, `daily` 같은 유지보수 경로는 raw 대화를 wiki 페이지로
통합하기 위해 small raw 문서 전체 또는 sampled raw 일부를 provider에 보낼 수 있습니다.
초대형 문서는 provider로 보내지 않고 skip합니다. 로컬 mirror/collect 단계만으로는 외부
AI 호출이 발생하지 않습니다.

## 자동 수집 vs opt-in 컬렉터

v0.15+ 의 외부 데이터 수집기 13종은 두 그룹으로 나뉩니다.

**자동 활성** — 설치만 하면 동작 (소스 부재면 자동 skip):

- Claude Code / Codex 세션 로그
- Cursor IDE / Continue.dev / Aider 세션
- Obsidian vault, Day One

**Opt-in 또는 권한 부여 필요** — 사용자가 명시적으로 활성화한 경우에만:

| 컬렉터 | 활성화 방법 | 비활성화 방법 |
| --- | --- | --- |
| `gmail_sent` | `SYNAPSE_GMAIL_ENABLE=1` + OAuth credentials 등록 | 환경변수 제거 |

모든 수집은 `~/.synapse/private/`(0700) 내부에 mirror 됩니다. 수집 자체는 외부 AI에
전송하지 않지만, 이후 ingest/backfill/watch가 wiki 통합을 수행할 때 small raw 또는
sampled raw를 provider로 보낼 수 있습니다. 질문 경로는 요약 카드와 사용자가 승인한
Profile/DecisionPatterns를 중심으로 전송합니다.

## AI가 마음대로 내 성향을 확정하나요?

아니요. `daily`와 `persona ingest`는 Profile 후보를 `MemoryInbox`에 만들 뿐입니다.
사용자가 Obsidian에서 검토하고 `Profile.md`나 `DecisionPatterns.md`로 옮긴 내용만
승인된 자료로 사용합니다.

이 흐름은 불편해 보일 수 있지만, 개인 메모리 도구에서는 중요한 안전 장치입니다.
AI가 잘못 추측한 내용을 곧바로 "나의 성향"으로 쓰지 않게 막습니다.

## 비용은 언제 발생하나요?

비용은 외부 AI를 호출할 때 발생합니다. 로컬 파일 이동, 진단, 설정 확인, cleanup scan
같은 작업은 별도 AI 비용이 들지 않습니다.

`daily` 같은 수집/통합 작업은 로컬 임베딩 없이 **대화 단위로 설정된 외부 AI provider(Codex 또는 Claude)를 호출**합니다.
따라서 수집 대상 데이터가 많을수록(예: Codex 세션 추가) 외부 AI 호출 횟수와 비용이 함께 늘어납니다.
"무료 로컬 색인"은 더 이상 없습니다.

| 작업 | 비용 감각 |
| --- | --- |
| 환경 점검 (`/sm:doctor`, `$doctor`, `synapse-memory doctor`) | 무료에 가까움 |
| 자동 복구 확인 (`/sm:fix`, `$fix`, `synapse-memory doctor --fix`) | 대부분 로컬 작업 |
| `synapse-memory daily --quick` | 적은 비용, 첫 체험용 (대화 단위 외부 AI 호출) |
| `synapse-memory daily` | 대화 단위로 외부 AI 호출 — 수집 소스(Claude/Codex 등)와 양에 따라 비용·시간 증가 |
| `synapse-memory ingest-audit --source codex` | 무료에 가까움 — pending queue 크기와 예상 호출 수만 로컬 계산 |
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
- Codex backfill 전에는 `synapse-memory ingest-audit --source codex --limit 50`으로
  pending queue의 `estimated_llm_calls`와 `oversize`를 먼저 확인합니다.
- 백필 비용을 더 낮춰 검증할 때는
  `synapse-memory ingest-audit --source codex --limit 50 --no-semantic-retrieval`로
  저비용 예상 호출 수를 확인한 뒤,
  `synapse-memory backfill --source codex --batch-size 5 --max-batches 1 --no-semantic-retrieval`
  처럼 작은 배치로 실행합니다.
- 수집 소스가 많을수록 대화 단위 외부 AI 호출이 늘어납니다. 불필요한 소스(예: Codex)는 비활성화해 호출 수를 줄입니다.
- 같은 질문을 반복하기 전에 카드와 Profile 후보를 먼저 검토합니다.
- 불필요한 draft와 오래된 MemoryInbox 후보는 Claude Code `/sm:cleanup`, Codex
  `$cleanup`, 또는 `synapse-memory cleanup scan`으로 정리 후보를 확인합니다.

ingest는 대형 문서 비용을 줄이기 위해 문서 크기별로 다르게 처리합니다. 40,000자
이하는 관련 페이지 선별 1회와 전체 본문 통합 1회로 보통 2회 호출합니다. 40,000자를
넘고 120,000자 이하인 문서는 관련 페이지 선별을 끄고 20,000자 이내 샘플만 1회
통합합니다. 120,000자를 넘는 초대형 문서는 외부 AI에 보내지 않고 skip하며, 같은
파일을 무한 재시도하지 않도록 watermark를 전진시킵니다.

`--no-semantic-retrieval`은 40,000자 이하 문서에서도 관련 페이지 선별 호출을 생략해
호출 수를 줄입니다. 대신 기존 페이지를 갱신할지 새 페이지를 만들지 판단하는 품질은
기본 모드보다 낮을 수 있습니다.

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

Obsidian vault 안의 요약 카드와 초안은 사용자가 직접 지웁니다.

```text
20_Reference/Projects/
20_Reference/Companies/
30_Creative/Drafts/
90_System/AI/
```

삭제 전에는 필요한 카드와 초안이 없는지 Obsidian에서 먼저 확인하세요.
