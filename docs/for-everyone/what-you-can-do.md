# Synapse로 무엇을 할 수 있나요?

> 실제로 매일·매주 어떤 명령을 어떻게 쓰는지 보여드립니다.
> *왜* 이게 필요한지는 [5가지 답답함을 어떻게 풀었나](how-it-works.md)에서.

모든 명령은 Claude Code 또는 Codex 채팅 안에서 `/synapse-*` 슬래시로 호출합니다.
터미널을 열 필요가 없습니다.

---

## 먼저 알아둘 두 가지 "받은편지함"

이름이 비슷해서 자주 헷갈리는 두 폴더가 있습니다. 시작 전에 구분해두면 이후 설명이 훨씬 잘 따라옵니다.

| 구분 | `00_Inbox/` | `90_System/AI/MemoryInbox/` |
|---|---|---|
| **누가 만드나** | 사용자가 직접 (Obsidian 새 노트 기본 위치) | Synapse가 자동 (`/synapse-daily` 마지막 단계) |
| **무엇이 들어 있나** | 정리 안 된 새 노트·메모 | "이 사람은 이런 성향·결정 패턴 같다" AI 후보 |
| **어디에 쓰이나** | 일단 던져두는 임시함 → 나중에 `10_Active/`로 분류 | 매일 검토 → 맞으면 `Profile.md` / `DecisionPatterns.md`로 옮김 |
| **카드 자동 생성?** | ❌ cluster로 안 묶임 → 카드 안 생김 | (해당 없음 — 카드가 아니라 ProfileFact 후보를 담음) |
| **별칭으로 부를 때** | "Inbox 폴더" / "받은편지함" | "MemoryInbox" / "메모리 인박스" |

**한 줄 요약**:
> 📥 `00_Inbox/`는 *내가 노트를 던지는 곳*,
> 💡 `MemoryInbox/`는 *AI가 나에 대한 후보를 두는 곳*.

> 자세한 vault 폴더 구조는 [동작 원리 — 내 노트는 vault 어디에 두면 되나요?](how-it-works.md#내-노트는-vault-어디에-두면-되나요), 정의는 [용어집 — Vault 폴더 컨벤션](../glossary.md#vault-폴더-컨벤션) 참고.

---

## 매일 5분 워크플로 ⏱️

> 매일 한 번만 누르면 됩니다.

```text
/synapse-daily
```

1~3분 안에 끝나고, 결과는 Obsidian vault 안에 만들어집니다.

```text
20_Reference/Projects/         ← 새/갱신된 프로젝트 카드
20_Reference/Companies/        ← 새/갱신된 회사 카드
90_System/AI/MemoryInbox/      ← "이 사람 이런 성향 같다" 후보
```

> 💡 카드가 자동으로 생기려면 노트가 **`10_Active/<회사>/<프로젝트>/`** 같은 cluster 가능한 경로에 있어야 합니다. `00_Inbox/`에만 쌓아두면 mirror만 되고 카드는 안 만들어집니다. 자세히: [내 노트는 vault 어디에 두면 되나요?](how-it-works.md#내-노트는-vault-어디에-두면-되나요)

### 나의 5분 일과

1. Obsidian에서 **MemoryInbox** 새 파일을 연다 (Profile-2026-05-13.md 같은)
2. 맞는 **ProfileFact**는 `90_System/AI/Profile.md`로 옮긴다
3. 맞는 **DecisionPattern**은 `90_System/AI/DecisionPatterns.md`로 옮긴다
4. 새 카드가 보이면 한 번 읽고, 맞으면 frontmatter `status`를 `draft` → `active`로 바꾼다

> 💡 처음 며칠은 AI가 만든 내용을 그대로 믿지 마세요.
> "내가 검토해서 옮긴 것만 진실원본"이라는 흐름이 이 도구의 정확도를 지킵니다.

---

## 1. 내 자료에 자연어로 묻기 — `/synapse-ask`

가장 자유로운 질문 명령. 의미 검색 + 키워드 검색을 합쳐서 관련 카드를 찾아 답합니다.

### 예시 1 — 과거 기술 결정 회상

```text
/synapse-ask "iOS 클린 아키텍처 어떻게 도입했지?"

Domain–Data–Presentation 3계층 + Repository + DIContainer 조합으로 도입.
도입 기간 2024.01~05, Tuist 멀티 모듈화로 확장 (2024.03~07).
결과: 버그 수정 시간 71% 단축, 크래시율 2.1% → 0.8%.
출처: [이력서-2026], [sample-ios-app]
```

### 예시 2 — 특정 종류만 검색

```text
/synapse-ask "어떤 회사에 관심 있었지?" --kind company
/synapse-ask "기술 스택 전반을 정리해줘" --kind project --top-k 8
```

### 예시 3 — 회사명 같은 고유명사 검색 (hybrid 모드)

```text
/synapse-ask "샘플회사B 경험" --hybrid

자료상 샘플회사B 관련 직접 경험은 확인되지 않습니다.
회사 카드는 기본 정보만 있고, 매칭되는 프로젝트 본문은 미작성 상태입니다.
출처: [examplecorp]
```

> 자료에 없는 내용은 *"자료에 없음"*이라고 답하도록 설계되어 있어, AI가 지어내는 답(환각)을 줄여 줍니다.

---

## 2. "내가 예전에 이거 어떻게 생각했지?" — `/synapse-recall`

시간순 회상에 특화된 명령. 같은 주제가 *언제 어떻게 변했는지* 보여줍니다.

```text
/synapse-recall "TCA 아키텍처"

2023.07 — 첫 검토, "러닝커브 vs 일관성" 트레이드오프 정리
2023.09 — 사이드 프로젝트에서 도입 시도, viewModifier 충돌 보고
2024.02 — 팀 합의 "현재 규모(앱 3개)에서는 ROI 부족" 결론
2024.11 — 신규 멤버 온보딩 후 재논의, 결정 유지

출처: [decisions-2023], [team-meeting-09], [retrospective-2024]
```

### 좋은 질문 예시

```text
/synapse-recall "샘플회사A에서 한 일"
/synapse-recall "AI 코딩 도구 사용 경험"
/synapse-recall "은퇴 자금 계획"
/synapse-recall "사이드 프로젝트 정리"
```

---

## 3. 회사 맞춤 이력서 — `/synapse-resume`

회사 카드 + 내 프로젝트 카드를 매칭해서 이력서 초안을 만듭니다.

```text
/synapse-resume 샘플회사B

✓ 이력서 생성: 30_Creative/Drafts/Resume - 샘플회사B (2026-05).md
  매칭 카드 6개: sample-ios-app, 이력서-2026, mobile-ios-tablet-app, ...
  강조: iOS 클린 아키텍처, 모바일 결제, 사용자 1M+ 트래픽 경험
  추정 비용: $0.42
```

### 품질을 높이는 순서

1. **회사 카드 보강** — Obsidian에서 `20_Reference/Companies/<회사>.md`를 열어 *기술 스택 / 포지션 / 원하는 경험* 키워드를 채움
2. **색인 갱신** — 백그라운드에서 자동, 강제로 갱신하려면:
   ```text
   /synapse-ask "rag index --rebuild로 색인을 다시 만들어줘"
   ```
3. **이력서 생성 다시 실행** — `/synapse-resume <회사>`
4. **본인 확인** — Obsidian `30_Creative/Drafts/`에서 수치·문장·민감 정보 확인 후 제출

> ⚠️ 이력서는 *초안*입니다. 지원 전 본인이 반드시 다듬어야 합니다.
> AI는 사실관계를 종종 약간 윤색합니다.

---

## 4. 의사결정 코파일럿 — `/synapse-decide`

승인된 Profile/DecisionPatterns가 채워질수록 가치가 커집니다.

```text
/synapse-decide "이력서를 sonnet으로 쓸까 opus로 쓸까?"

[Profile/Patterns 사용 ✓]

당신의 평소 결정 패턴 (DecisionPatterns에서):
- "비용보다 품질 우선" (이력서·계약서 등 결과물 중요도 높음)
- "사용 빈도 낮은 작업은 비싼 모델 OK" (월 1~2회)

→ 권장: opus
근거: 이력서는 채용 결과에 직접 영향, 월 사용량 적음(과거 평균 3회/월)
```

### 출력 신호 읽기

| 출력 | 의미 |
|---|---|
| `[Profile/Patterns 사용 ✓]` | 승인된 자료로 결정 → 신뢰도 높음 |
| `[Profile 없음 - 일반 모드]` | 판단 재료 부족 → 일반적인 권장만 |

### Profile 자료 늘리기

```text
/synapse-ask "프로필 후보 추출해줘"
```

또는 매일 `/synapse-daily`가 자동으로 후보를 `MemoryInbox`에 추가합니다.
내가 검토해서 `Profile.md`로 옮긴 것만 의사결정에 쓰입니다.

---

## 5. 새 프로젝트·회사 미리 등록 — Obsidian에서 직접

빈 카드를 먼저 만들어 직접 채우는 것도 가능합니다.

```text
/synapse-ask "프로젝트 카드 my-new-project, 제목 '내 새 프로젝트' 만들어줘"
/synapse-ask "회사 카드 acme, 제목 'Acme Corp' 만들어줘"
```

또는 vault에 새 노트를 작성하고 다음 `/synapse-daily` 실행 때 자동으로 cluster를 인식하도록 둡니다. 보통 *같은 폴더 안에 노트가 2개 이상* 있으면 cluster로 잡힙니다.

---

## 6. NDA 회사명·프로젝트명 절대 차단 — redact-list

외부 AI에 절대 보내고 싶지 않은 단어를 등록합니다.

```text
/synapse-ask "redact-list에 '비공개사명' 추가해줘"
/synapse-ask "redact-list 현재 상태 보여줘"
```

또는 터미널:

```bash
synapse-memory redactlist add "비공개사명"
synapse-memory redactlist add "프로젝트X"
synapse-memory redactlist show
```

추가된 항목은 마스킹의 **가장 첫 단계**에서 `[REDACT_*]` 형태로 치환되어, 어떤 경로로도 외부에 나갈 수 없습니다.

---

## 7. 환경이 깨졌을 때 — `/synapse-doctor` / `/synapse-fix`

```text
/synapse-doctor

✓ apfel 설치: /opt/homebrew/bin/apfel
✓ Apple Silicon (arm64)
✓ macOS 26.x (Tahoe+)
✓ L0 루트: /Users/<you>/.synapse/private (0700)
✓ Claude Code CLI: ... (model=sonnet)
✓ Codex launchd 데몬: 실행 중
✓ 준비 완료
```

뭔가 실패하면:

```text
/synapse-fix
```

자동 복구 가능한 항목만 시도합니다(vault 권한, L0 폴더 권한, 로그 디렉터리 등). 운영 단계의 메모리 쓰기는 수행하지 않으므로 안전합니다.

---

## 슬래시 명령 한눈에 보기

| 명령 | 언제 쓰나 | 결과 |
|---|---|---|
| `/synapse-onboard` | **처음 설치 직후, 뭐부터 해야 할지 모를 때** | 답답함 1개를 골라 끝까지 체험 |
| `/synapse-assistant` | **매일 진입 — 오늘 뭐 할지 추천받고 싶을 때** | 1~3개 추천 + 동의 시 대신 실행 |
| `/synapse-cleanup` | **vault가 어지러워졌을 때 (월 1회 권장)** | 오래된·휴면·빈 자료를 archive로 이동 (영구 삭제 0건) |
| `/synapse-config` | **cleanup 임계값·모델·top_k 등 사용자 설정 변경** | 자연어로 한 키 변경 + 백업 자동 |
| `/synapse-daily` | 하루 한 번 정리 | 새 카드 + MemoryInbox 후보 |
| `/synapse-ask <질문>` | 내 자료에서 답을 찾고 싶을 때 | 답변 + 출처 카드 |
| `/synapse-recall <주제>` | 시간순 회상이 필요할 때 | 시간순 변화 |
| `/synapse-decide <상황>` | 결정에 도움이 필요할 때 | 권장안 + 근거 |
| `/synapse-resume <회사>` | 회사 맞춤 이력서를 만들고 싶을 때 | Obsidian에 초안 |
| `/synapse-feedback` | 카드 품질 평가 | 다음 색인에 반영 |
| `/synapse-cost` | 비용 요약 | 30일 누적 |
| `/synapse-doctor` | 환경 점검 | 진단 결과 |
| `/synapse-fix` | 자동 복구 시도 | 복구 결과 |

---

## 매주·매월 추천 흐름

| 주기 | 할 일 |
|---|---|
| 매일 (5분) | `/synapse-daily` → MemoryInbox 검토 → 카드 status 확인 |
| 매주 (15분) | Profile.md / DecisionPatterns.md 다듬기, 회사 카드 키워드 보강 |
| 매월 (30분) | `/synapse-resume`으로 자기 정리 시도 + `/synapse-cost`로 비용 점검 |
| 분기 (1시간) | 오래된 카드 정리·삭제, redactlist 갱신 |

---

## 다음에 읽을 문서

- [5가지 답답함을 어떻게 풀었나](how-it-works.md) — 왜 이 명령들이 있는지
- [개인정보 · 비용 · 삭제 FAQ](privacy-and-cost.md) — 가장 자주 묻는 우려
- [사용 시나리오 (CLI 버전)](../usage.md) — 명령 옵션의 더 깊은 흐름
- [CLI 레퍼런스](../commands.md) — 모든 명령 옵션
