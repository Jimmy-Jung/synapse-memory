# 사용 시나리오

이 문서는 설치가 끝난 뒤 실제로 Synapse Memory를 어떻게 쓰는지 설명합니다. 명령 옵션 전체가 필요하면 [CLI 명령 레퍼런스](commands.md)를 보세요.

> 각 시나리오는 **CLI** 와 **Slash** 두 가지 호출 방식을 함께 보여줍니다. 둘은 같은 백엔드를 호출하므로 결과가 동일합니다.
>
> | 시나리오 | CLI | Slash |
> | --- | --- | --- |
> | 일일 통합 | `synapse-memory daily` | `/synapse-daily` |
> | 자연어 질의 | `synapse-memory ask "..."` | `/synapse-ask ...` |
> | 시간순 회상 | `synapse-memory me what-did-i-think "..."` | `/synapse-recall ...` |
> | 의사결정 | `synapse-memory me decide "..."` | `/synapse-decide ...` |
> | 이력서 | `synapse-memory me draft-resume <slug>` | `/synapse-resume <slug>` |
> | 환경 진단 | `synapse-memory doctor` | `/synapse-doctor` |
> | 환경 복구 | `synapse-memory doctor --fix` | `/synapse-fix` |

## 1. 매일 5분 워크플로

가장 자주 쓰는 명령입니다.

```bash
synapse-memory daily --profile-facts-only
```

이 한 줄은 다음 일을 순서대로 처리합니다.

1. Claude Code 활동 로그 수집
2. Obsidian vault 변경분 수집
3. 새 cluster 분류
4. 필요한 Card 생성
5. Card 검색 인덱스 갱신
6. Profile 후보를 `MemoryInbox`에 작성

결과는 vault 안에 생깁니다.

```text
90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md
20_Reference/Projects/*.md
20_Reference/Companies/*.md
```

매일 할 일은 간단합니다.

1. `MemoryInbox`의 새 파일을 열어 봅니다.
2. 맞는 ProfileFact는 `90_System/AI/Profile.md`로 옮깁니다.
3. 맞는 DecisionPattern은 `90_System/AI/DecisionPatterns.md`로 옮깁니다.
4. 새 Card가 있으면 내용과 `status`를 확인합니다.

처음에는 자동 생성 내용을 바로 믿기보다, Obsidian에서 한 번 검토한 것만 “진실원본”으로 올리는 흐름을 권장합니다.

## 2. 내 자료에 질문하기

가장 자유로운 질문 endpoint입니다.

```bash
synapse-memory ask "iOS 개발에서 클린 아키텍처를 어떻게 적용했지?"
```

특정 종류의 Card만 검색할 수도 있습니다.

```bash
synapse-memory ask "어떤 회사에 관심 있었지?" --kind company
synapse-memory ask "기술 스택 전반을 정리해줘" --kind project --top-k 8
```

답변에는 근거가 된 Card ID가 함께 표시됩니다. 검색 결과가 빈약하면 먼저 Card를 검토하고 다시 인덱싱합니다.

```bash
synapse-memory card list
synapse-memory rag index --rebuild
```

## 3. 과거의 내 생각 회상하기

“내가 예전에 이 주제에 대해 뭐라고 생각했지?”에 가까운 기능입니다.

```bash
synapse-memory me what-did-i-think "TCA 아키텍처"
```

좋은 질문 예시는 다음과 같습니다.

```bash
synapse-memory me what-did-i-think "샘플회사에서 한 일"
synapse-memory me what-did-i-think "AI 코딩 도구 사용 경험"
synapse-memory me what-did-i-think "은퇴 자금 계획"
```

답변은 보통 핵심 요약, 시간순 변화, 근거 Card 인용으로 구성됩니다. 자료에 없는 내용은 없다고 말하도록 설계되어 있습니다.

## 4. 의사결정 도움 받기

`me decide`는 Profile과 DecisionPatterns가 채워질수록 가치가 커집니다.

```bash
synapse-memory me decide "이력서를 sonnet으로 작성할까 opus로 작성할까?"
```

출력에 `(Profile/Patterns 사용 ✓)`가 보이면 승인된 Profile 자료를 사용한 것입니다. `(Profile 없음 - 일반 모드)`가 보이면 아직 판단 재료가 부족한 상태입니다.

Profile 자료를 만들려면 다음 흐름을 사용합니다.

```bash
synapse-memory me update-profile --facts-only
```

그 뒤 `MemoryInbox`에 생성된 후보를 직접 검토해서 `Profile.md`나 `DecisionPatterns.md`로 옮깁니다.

## 5. 회사 맞춤 이력서 만들기

회사 Card와 프로젝트 Card를 바탕으로 이력서 초안을 만듭니다.

```bash
synapse-memory me draft-resume danggeun --model sonnet
```

출력 파일은 vault 안에 생성됩니다.

```text
30_Creative/Drafts/Resume - <회사> (YYYY-MM).md
```

품질을 높이는 순서는 이렇습니다.

1. `synapse-memory card show danggeun --type company`로 회사 Card를 확인합니다.
2. 회사 키워드, 포지션, 원하는 경험이 비어 있으면 Obsidian에서 보강합니다.
3. `synapse-memory rag index --rebuild`로 인덱스를 갱신합니다.
4. `me draft-resume`을 다시 실행합니다.

생성된 이력서는 초안입니다. 지원 전에 반드시 문장, 수치, 민감 정보를 직접 확인합니다.

## 6. 새 프로젝트나 회사 추가하기

빈 Card를 먼저 만들어 직접 채울 수 있습니다.

```bash
synapse-memory card new my-new-project "내 새 프로젝트"
synapse-memory card new acme "Acme Corp" --type company
```

또는 vault에 새 노트를 작성하고 `daily`가 자동으로 cluster를 찾게 둘 수 있습니다. 프로젝트 폴더에 노트가 2개 이상 있으면 cluster로 잡힐 가능성이 높습니다.

## 7. NDA 키워드 마스킹하기

외부 LLM에 절대 보내고 싶지 않은 회사명, 프로젝트명, 키워드는 redact-list에 추가합니다.

```bash
synapse-memory redactlist add "비공개사명"
synapse-memory redactlist add "프로젝트X"
synapse-memory redactlist show
```

추가된 항목은 redaction의 가장 앞 단계에서 `[REDACT_*]` 형태로 치환됩니다.

## 8. 다시 만들기와 백필

큰 변경 후 처음부터 다시 만들고 싶을 때만 사용합니다.

```bash
synapse-memory card generate --force --kind all
synapse-memory rag index --rebuild
```

Claude Code raw 전체에 redaction을 다시 적용하려면 시간이 오래 걸릴 수 있습니다.

```bash
synapse-memory redact backfill claude-code --resume
```

작게 시험하려면 제한을 둡니다.

```bash
synapse-memory redact backfill claude-code --limit 3 --max-bytes-per-file 50000
```

## 비용 감각

로컬 작업인 collect, redaction Pass 1, RAG index 자체는 Claude 비용이 들지 않습니다. Claude Code CLI를 부르는 classify, card generate, ask, me 계열 명령은 사용량이 발생할 수 있습니다.

| 작업 | 대략적인 비용 감각 |
| --- | --- |
| `daily`에서 변경이 거의 없음 | 거의 없음 |
| `daily --profile-facts-only` | 낮음 |
| `cluster classify --resume` | 낮음, 기본 haiku |
| `card generate` | Card 수에 비례 |
| `ask`, `me decide`, `me what-did-i-think` | 질문 길이와 검색 결과 수에 비례 |
| `me draft-resume` | 이력서 1개 단위로 발생 |

정확한 비용은 Claude Code의 모델, 구독, 내부 과금 정책에 따라 달라질 수 있습니다.

## 다음에 볼 문서

- [CLI 명령 레퍼런스](commands.md): 옵션 전체
- [아키텍처](architecture.md): raw가 어떻게 보호되는지
- [개발자 가이드](development.md): 새 기능을 추가하는 법

## 환경이 깨졌을 때

설치 후 LaunchAgent, runtime shim, `~/.synapse/private` 권한 같은 환경 문제가 생기면 먼저 진단합니다.

```bash
synapse-memory doctor
```

자동 복구 가능한 항목만 고치려면 다음 명령을 사용합니다.

```bash
synapse-memory doctor --fix
```

이 명령은 whitelisted repair만 실행하며, 운영 단계의 메모리 쓰기는 수행하지 않습니다.
