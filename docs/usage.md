# 사용 시나리오

이 문서는 설치가 끝난 뒤 실제로 Synapse Memory를 어떻게 쓰는지 설명합니다. 명령 옵션 전체가 필요하면 [CLI 명령 레퍼런스](commands.md)를 보세요.

## 어떤 답답함에 어느 절을 보면 되나

| 답답함 | 어느 절 | 핵심 명령 |
|---|---|---|
| "노트가 매일 쌓이는데 정리할 시간이 없다" | [§1 매일 5분 워크플로](#1-매일-5분-워크플로) | `daily` |
| "Obsidian 검색해도 그 노트가 안 나온다" | [§2 내 자료에 질문하기](#2-내-자료에-질문하기) | `ask` |
| "작년 결정 이유가 기억 안 난다" | [§3 과거의 내 생각 회상하기](#3-과거의-내-생각-회상하기) | `persona what-did-i-think` |
| "사소한 결정에 매일 피로하다" | [§4 의사결정 도움 받기](#4-의사결정-도움-받기) | `persona decide` |
| "회고록·일기를 학습시켜서 비서/세컨드브레인처럼 쓰고 싶다" | [§4a 외부 자료 학습시키기](#4a-외부-자료-학습시키기) | `persona ingest` |
| "회사마다 이력서를 6시간씩 다시 쓴다" | [§5 회사 맞춤 이력서 만들기](#5-회사-맞춤-이력서-만들기) | `persona draft-resume` |
| "새 프로젝트를 내 기술 스택으로 빠르게 설계하고 싶다" | [§5a 새 프로젝트 설계 초안](#5a-새-프로젝트-설계-초안) | `persona design-project` |
| "새 프로젝트 카드를 미리 만들고 싶다" | [§6 새 프로젝트나 회사 추가하기](#6-새-프로젝트나-회사-추가하기) | `card new` |
| "이 회사명은 절대 외부에 보내지 마" | [§7 NDA 키워드 마스킹하기](#7-nda-키워드-마스킹하기) | `redactlist add` |
| "색인을 처음부터 다시 만들고 싶다" | [§8 다시 만들기와 백필](#8-다시-만들기와-백필) | `rag index --rebuild` |
| "새 노트를 어디 폴더에 둬야 카드가 생기나" | [vault 폴더 컨벤션](#vault-폴더-컨벤션--노트를-어디에-두면-카드가-생기나) | (폴더 규칙) |
| "비용이 얼마나 드는지 가늠이 안 된다" | [비용 감각](#비용-감각) | `cost summary` |
| "환경이 깨졌다 / doctor가 실패한다" | [환경이 깨졌을 때](#환경이-깨졌을-때) | `doctor --fix` |

> 각 시나리오는 **CLI** 와 **Slash** 두 가지 호출 방식을 함께 보여줍니다. 둘은 같은 백엔드를 호출하므로 결과가 동일합니다.
>
> | 시나리오 | CLI | Slash |
> | --- | --- | --- |
> | 일일 통합 | `synapse-memory daily` | `/synapse-daily` |
> | 자연어 질의 | `synapse-memory ask "..."` | `/synapse-ask ...` |
> | 시간순 회상 | `synapse-memory persona what-did-i-think "..."` | `/synapse-recall ...` |
> | 의사결정 | `synapse-memory persona decide "..."` | `/synapse-decide ...` |
> | 외부 자료 학습 | `synapse-memory persona ingest --file <path>` | (CLI only) |
> | 이력서 | `synapse-memory persona draft-resume <slug>` | `/synapse-resume <slug>` |
> | 프로젝트 설계 초안 | `synapse-memory persona design-project "<아이디어>"` | (CLI only) |
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

### Quick mode — 첫 호출과 매일 routine 용

첫 호출의 30분~1시간이 부담되거나, 매일 가벼운 갱신만 필요할 때 `--quick` 플래그를 씁니다. 최근 7일 modified 노트만 mirror하고 (전체 대비 89% 감소), classify는 최대 10 cluster까지만, `update_profile` 단계는 자동 skip합니다. 첫 호출도 약 **3분 안에** 끝납니다.

```bash
synapse-memory daily --quick                          # 기본: 7일 cutoff, 10 cluster cap
synapse-memory daily --quick --quick-days 14          # cutoff 를 2주로 늘림
synapse-memory daily --quick --quick-max-clusters 20  # cluster cap 을 20개로 늘림
synapse-memory daily                                  # full — 매주 1회 또는 수동
```

**언제 quick / 언제 full 인가**

| 상황 | 모드 |
| --- | --- |
| 처음 설치 후 첫 답변까지 빨리 가고 싶음 | `daily --quick` |
| 매일 routine (변경 노트만 반영) | `daily --quick` |
| 매주 1회 vault 전체 재정리 | `daily` (full) |
| `Profile.md`·`DecisionPatterns.md` 갱신이 필요 | `daily` (full) |
| 큰 백필·재인덱싱 후 정합성 회복 | `daily` (full) |

**cron 분리 예** — 매일 quick, 일요일 새벽에만 full:

```cron
# 매일 09:00 quick (최근 변경분만 반영, ~3분)
0 9 * * *  /opt/homebrew/bin/synapse-memory daily --quick

# 일요일 03:00 full (Profile/DecisionPatterns 후보 포함, 30분~1시간)
0 3 * * 0  /opt/homebrew/bin/synapse-memory daily
```

> ⚠️ **`daily --quick`과 `daily` (full)을 동시에 실행하지 마세요.** 두 프로세스가 같은 ChromaDB 컬렉션에 동시에 쓰면 인덱스가 깨질 수 있습니다. cron 일정을 짤 때도 둘이 겹치지 않도록 시간 간격을 충분히 두세요. 한 번 켜진 daily가 끝났는지는 `synapse-memory daily-status` 로 확인합니다.

### 진행 상황 확인

첫 실행이거나 새 노트가 많이 쌓인 날에는 `daily`가 30분~1시간씩 걸릴 수 있습니다. 진행 상황은 두 가지 방식으로 확인할 수 있습니다.

1. **터미널 실시간 출력** — 클러스터 단위로 `[i/N] cluster_id ... ok (12.3s)` 형식으로 한 줄씩 출력됩니다.
2. **status 파일 polling** — 별도 터미널이나 Claude Code 데스크탑 / Codex처럼 stdout이 가려진 환경에서:

   ```bash
   synapse-memory daily-status            # 한 번 조회
   synapse-memory daily-status --watch    # 2초 간격으로 추적
   cat ~/.synapse/run/daily.status.json   # AI agent용 원본
   ```

자세한 형식과 옵션은 [CLI 레퍼런스의 `daily-status`](commands.md#daily-status)를 참고하세요.

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
synapse-memory persona what-did-i-think "TCA 아키텍처"
```

좋은 질문 예시는 다음과 같습니다.

```bash
synapse-memory persona what-did-i-think "샘플회사에서 한 일"
synapse-memory persona what-did-i-think "AI 코딩 도구 사용 경험"
synapse-memory persona what-did-i-think "은퇴 자금 계획"
```

답변은 보통 핵심 요약, 시간순 변화, 근거 Card 인용으로 구성됩니다. 자료에 없는 내용은 없다고 말하도록 설계되어 있습니다.

## 4. 의사결정 도움 받기

`persona decide`는 Profile과 DecisionPatterns가 채워질수록 가치가 커집니다.

```bash
synapse-memory persona decide "이력서를 sonnet으로 작성할까 opus로 작성할까?"
```

출력에 `(Profile/Patterns 사용 ✓)`가 보이면 승인된 Profile 자료를 사용한 것입니다. `(Profile 없음 - 일반 모드)`가 보이면 아직 판단 재료가 부족한 상태입니다.

Profile 자료를 만들려면 다음 흐름을 사용합니다.

```bash
synapse-memory persona update-profile --facts-only
```

그 뒤 `MemoryInbox`에 생성된 후보를 직접 검토해서 `Profile.md`나 `DecisionPatterns.md`로 옮깁니다.

## 4a. 외부 자료 학습시키기

회고록·일기·기획서 초안 같은 **vault 밖 markdown / txt 파일**을 Persona 에 흡수시킬 수 있습니다. 본인 말투, 기술 선호, 작업 방식이 Profile 에 두텁게 쌓일수록 `persona decide`·`persona design-project` 같은 후속 명령의 결과 품질이 올라갑니다.

```bash
synapse-memory persona ingest --file ~/Documents/diary-2025.md
synapse-memory persona ingest \
    --file ~/Documents/retro-q4.md \
    --file ~/Documents/proposal-draft.md
```

흐름:

1. raw 텍스트는 `~/.synapse/private/raw/persona/<sha-prefix>/<파일명>` 에 0600 으로 mirror 됩니다. vault 에는 절대 raw 가 노출되지 않습니다.
2. Pass 1 + Pass 2 redaction 통과한 텍스트로 ProfileFact 후보를 추출합니다.
3. 후보는 `90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md` 에 PR 로 append 됩니다. `persona update-profile` 과 같은 파일을 공유하므로 한 번에 검토 가능합니다.
4. Obsidian 에서 PR 을 열어 accepted 항목만 `Profile.md` 로 직접 복사합니다.

지원 확장자: `.md`, `.markdown`, `.txt`. PDF·docx 는 현재 unsupported — fail-fast 로 안내됩니다.

> 💡 `voice` 카테고리는 외부 자료에서 가장 잘 잡힙니다 (말투·문장 길이·표현 선호). claude history 만으로는 voice 추출이 빈약합니다.

## 5. 회사 맞춤 이력서 만들기

회사 Card와 프로젝트 Card를 바탕으로 이력서 초안을 만듭니다.

```bash
synapse-memory persona draft-resume examplecorp --model sonnet
```

출력 파일은 vault 안에 생성됩니다.

```text
30_Creative/Drafts/Resume - <회사> (YYYY-MM).md
```

품질을 높이는 순서는 이렇습니다.

1. `synapse-memory card show examplecorp --type company`로 회사 Card를 확인합니다.
2. 회사 키워드, 포지션, 원하는 경험이 비어 있으면 Obsidian에서 보강합니다.
3. `synapse-memory rag index --rebuild`로 인덱스를 갱신합니다.
4. `persona draft-resume`을 다시 실행합니다.

생성된 이력서는 초안입니다. 지원 전에 반드시 문장, 수치, 민감 정보를 직접 확인합니다.

## 5a. 새 프로젝트 설계 초안

"이런 아이디어로 새 프로젝트 시작" 이라고 할 때, **본인 기술 스택 · 작업 방식 · 말투** 가 반영된 설계 markdown 을 `20_Projects/Drafts/` 에 만듭니다. ChatGPT 일반 답변이 아니라 "내가 직접 쓴 것 같은" 초안이 목표입니다.

```bash
synapse-memory persona design-project "iOS Todo 앱 새로 시작"
synapse-memory persona design-project "사내 RAG 검색 도구" --top-k 8
```

출력 파일:

```text
20_Projects/Drafts/design_project - <아이디어> (YYYY-MM-DD).md
```

내용 구성 (Profile 의 `domain` 에 따라 섹션 가이드 자동 선택):

1. 요약
2. 추천 기술 스택 — `[Profile: tech]` 인용 강제
3. 아키텍처 개요
4. 단계별 진행 — `[Profile: work_style]` 인용
5. 유사 과거 프로젝트 — ProjectCard RAG hit 인용 (`[card_id]`)
6. 첫 주 작업 (3-5개)
7. 유의사항 — Profile 에 weakness 가 있으면 인용

품질을 결정하는 두 변수:

- **Profile 두께**: `tech` / `work_style` / `voice` 카테고리에 fact 가 최소 2-3개씩 있을 때 데모 가치가 큽니다. 비어있으면 출력 상단에 nudge 메시지가 뜨고 generic 추천만 나옵니다.
- **ProjectCard RAG 인덱스**: 유사 과거 프로젝트가 있어야 학습 포인트 인용이 풍부해집니다. `synapse-memory rag index` 가 최신인지 확인하세요.

권장 선행 작업:

```bash
synapse-memory persona ingest --file ~/Documents/회고록.md
synapse-memory persona update-profile
# Obsidian 에서 MemoryInbox PR 검토 후 Profile.md 에 반영
synapse-memory rag index
synapse-memory persona design-project "<아이디어>"
```

> 출력에 사용자가 안 쓰는 프레임워크 (React/Flutter 같은) 가 등장하지 않아야 정상. 등장한다면 Profile.md 의 tech fact 가 부족하다는 신호 — `persona update-profile` 보강 후 재시도.

## 6. 새 프로젝트나 회사 추가하기

빈 Card를 먼저 만들어 직접 채울 수 있습니다.

```bash
synapse-memory card new my-new-project "내 새 프로젝트"
synapse-memory card new acme "Acme Corp" --type company
```

또는 vault에 새 노트를 작성하고 `daily`가 자동으로 cluster를 찾게 둘 수 있습니다. 프로젝트 폴더에 노트가 2개 이상 있으면 cluster로 잡힐 가능성이 높습니다. **어느 폴더에 노트를 두느냐가 cluster 인식에 직접 영향**을 주므로, 다음 절의 vault 폴더 컨벤션을 먼저 참고하세요.

## vault 폴더 컨벤션 — 노트를 어디에 두면 카드가 생기나

Synapse는 [PARA Method](https://fortelabs.com/blog/para/)와 [Johnny.Decimal](https://johnnydecimal.com/)을 섞은 vault 구조(`00_Inbox` / `10_Active` / `20_Reference` / `30_Creative` / `90_System`)를 가정합니다. *왜 이 변형을 골랐고 어디까지 강제되는지*는 [설계 개요의 "왜 이런 폴더 구조를 골랐나요?"](for-everyone/architecture-overview.md#왜-이런-폴더-구조00_inbox-10_active--를-골랐나요)를 보세요.

각 폴더는 **누가 만들고 누가 사용하는지**가 다릅니다.

| 폴더 | 누가 만드나 | Synapse 동작 | 사용자 행동 |
|---|---|---|---|
| `00_Inbox/` | **사용자** (Obsidian의 새 노트 기본 위치) | mirror만 — 특별 처리 없음 | 미정리 노트를 일시적으로 둠. 정리할 때 `10_Active/<회사>/<프로젝트>/`로 옮김 |
| `10_Active/<회사>/<프로젝트>/...` | **사용자** | **cluster 식별의 주된 소스** — 폴더 segment가 cluster_id로 변환됨 | 진행 중 프로젝트 노트를 여기에 둠 |
| `20_Reference/Projects/*.md` | **Synapse 자동 생성** (`card generate`) | ProjectCard 저장 | `status: draft` → 검토 후 `active`로 승격 |
| `20_Reference/Companies/*.md` | **Synapse 자동 생성** (`card generate`) | CompanyCard 저장 | 회사 카드 보강 (포지션·키워드) |
| `20_Projects/Drafts/` | **Synapse 자동 생성** (`persona design-project`) | 새 프로젝트 설계 초안 저장 | 다듬어서 `10_Active/...` 로 이동 |
| `30_Creative/Drafts/` | **Synapse 자동 생성** (`persona draft-resume`) | 이력서 초안 저장 | 다듬어서 사용 |
| `90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md` | **Synapse 자동 생성** (`update_profile`, `ingest`) | ProfileFact/DecisionPattern 후보 | 검토 후 `Profile.md` / `DecisionPatterns.md`로 승격 |
| `90_System/AI/{Profile,DecisionPatterns}.md` | **사용자가 승격** | `persona decide`의 의사결정 컨텍스트 | 진실원본으로 유지 |
| `90_System/AI/DailyReports/YYYY-MM-DD.md` | **Synapse 자동 생성** (daily `report` 단계) | 그날 단계별 status/elapsed/실패 로그 | 결과 검토 |
| `90_System/AI/recipes/` | 사용자 정의 (선택) | `persona generate <recipe>` | 커스텀 prompt recipe |

### `00_Inbox`의 용도와 한계

`00_Inbox`는 **사용자가 미정리 노트를 일시적으로 던지는 받은편지함**입니다. Obsidian이 새 노트 기본 위치로 자주 쓰는 폴더이고, GTD/PARA 컨벤션에서도 동일한 의미로 통용됩니다.

Synapse 관점에서는 다음과 같이 다룹니다.

- ✅ `collect_obsidian`이 다른 폴더와 동일하게 mirror합니다 (`~/.synapse/private/raw/obsidian/00_Inbox/...`).
- ⚠️ **cluster로는 잘 안 묶입니다.** cluster 식별은 폴더 segment(주로 `10_Active/<회사>/<프로젝트>`)를 신호로 쓰는데, `00_Inbox`는 평평한 잡탕 구조라 같은 cluster_id로 모이지 않습니다.
- ❌ 결과적으로 `00_Inbox`에만 쌓인 노트는 **자동으로 Card가 생기지 않습니다.**

### 권장 워크플로 — Inbox → Active

1. 새 생각/회의록은 일단 `00_Inbox/`에 두세요. 부담 없이.
2. 주 1회 또는 `/synapse-daily` 후 MemoryInbox 검토할 때 같이 정리합니다.
3. **카드화하고 싶은 노트**는 `10_Active/<회사>/<프로젝트>/` 경로로 옮깁니다.
4. 같은 폴더에 노트가 2개 이상 쌓이면 다음 `daily`에서 cluster로 잡혀 ProjectCard/CompanyCard가 자동 생성됩니다.
5. 더 이상 진행 중이 아닌 프로젝트는 별도 `40_Archive/` 같은 곳으로 옮겨두면 `10_Active` cluster에서 빠집니다 (단, mirror는 계속됨).

> 🚫 **`90_System/AI/`는 Synapse 전용입니다.** 사용자는 이 폴더 안의 내용을 읽고 승격(이동)할 수는 있지만, 직접 작성한 노트를 두지는 마세요. `daily`가 덮어쓸 수 있습니다. 기본 제외 정책상 mirror 대상에서도 빠집니다 (`commands.md:123`).

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
| `ask`, `persona decide`, `persona what-did-i-think` | 질문 길이와 검색 결과 수에 비례 |
| `persona ingest --file ...` | 파일 크기에 비례 (redaction Pass 2 + fact 추출 1회) |
| `persona draft-resume` | 이력서 1개 단위로 발생 |
| `persona design-project` | 초안 1개 단위 (Profile 텍스트 + RAG hit + 생성 1회) |

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
