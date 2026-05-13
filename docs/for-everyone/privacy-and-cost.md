# 개인정보 · 비용 · 삭제 FAQ

> 비개발자가 가장 많이 묻는 5가지 우려를 한 곳에 정리합니다.

## 어떤 우려에 어느 절을 보면 되나

| 우려 | 어느 절 |
|---|---|
| "내 노트·카톡·이메일이 외부로 새나가나?" | [§ 내 노트·카톡·대화 기록이 외부로 새나가나요?](#내-노트--카톡--대화-기록이-외부로-새나가나요) |
| "마스킹은 정확히 무엇을 가리나?" | [§ 마스킹은 무엇을 가리나요?](#마스킹은-무엇을-가리나요) |
| "특정 회사명·NDA 단어를 절대 보내고 싶지 않다" | [§ 특정 회사명·프로젝트명을 절대 보내고 싶지 않다면?](#특정-회사명프로젝트명을-절대-보내고-싶지-않다면) |
| "Claude Code 자격증명·API 키는?" | [§ Claude Code에는 어떤 권한을 주나요?](#claude-code에는-어떤-권한을-주나요) |
| "Codex 세션은 어떻게 수집되나?" | [§ Codex 세션 기록은 어떻게 수집되나요?](#codex-세션-기록은-어떻게-수집되나요) |
| "한 달에 얼마나 드나?" | [§ 비용](#비용) |
| "어떤 작업이 유료/무료?" | [§ 어떤 작업이 비용이 들고 어떤 작업이 무료인가요?](#어떤-작업이-비용이-들고-어떤-작업이-무료인가요) |
| "비용 줄이는 법은?" | [§ 비용을 줄이려면?](#비용을-줄이려면) |
| "노트북 분실·초기화 시 복구는?" | [§ 백업과 복구](#백업과-복구) |
| "완전히 삭제하려면?" | [§ 완전 삭제](#완전-삭제) |

## 개인정보

### 내 노트 · 카톡 · 대화 기록이 외부로 새나가나요?

**아니요.** 다음 3가지 원칙을 강제로 지킵니다.

1. **원본은 외부에 보내지 않음** — Obsidian 노트, Claude Code 대화(`~/.claude/projects/`), Codex 세션(`~/.codex/sessions/`)에서 가져온 모든 원본은 `~/.synapse/private/raw/`와 `~/.synapse/private/normalized/{claude,codex}/` 폴더에만 저장됩니다.
   이 폴더는 권한 `0700`(본인만 읽기/쓰기/실행)으로 보호되어, 같은 Mac의 다른 사용자도 접근할 수 없습니다.
2. **외부 AI에는 마스킹본 또는 검토된 카드만** — Claude(외부 AI)에 보내기 전에 항상 마스킹 단계를 거칩니다.
3. **사용자가 검토한 카드만 검색 대상** — 자동 생성된 카드는 `status: draft`이며,
   내가 직접 `status: active`로 바꾼 카드만 외부 검색에 쓰입니다.

### 마스킹은 무엇을 가리나요?

**1단계 — 정규식 (정확한 패턴):**

- 이메일 주소 (`example@domain.com`)
- 한국 전화번호 (`010-1234-5678`, `+82-2-…`)
- 신용카드 번호 (Luhn 체크 통과)
- 주민등록번호
- IP 주소
- JWT · AWS 키 · API 키 · Bearer 토큰
- 사용자가 추가한 NDA 키워드 (회사명, 프로젝트명 등)

**2단계 — 로컬 AI ([apfel](https://apfel.franzai.com), Apple FoundationModels):**

- 사람 이름
- 조직명·회사명
- 주소
- 민감한 주제
- 패스워드·비밀키

2단계는 **내 Mac 안에서만 실행**됩니다. 로컬 AI는 인터넷에 연결되지 않습니다.

### 특정 회사명·프로젝트명을 절대 보내고 싶지 않다면?

```text
/synapse-ask "redact-list에 '비공개사명' 추가"
```

또는 터미널에서:

```bash
synapse-memory redactlist add "비공개사명"
synapse-memory redactlist add "프로젝트X"
synapse-memory redactlist show
```

추가된 항목은 마스킹의 **가장 첫 단계**에서 `[REDACT_*]` 형태로 치환됩니다.

### Claude Code에는 어떤 권한을 주나요?

Claude Code의 기존 인증(OAuth)을 그대로 사용합니다.
**새 API 키 발급은 필요 없습니다.** Synapse는 Claude Code CLI를 단순히 호출할 뿐,
당신의 Claude 계정 자격증명을 따로 읽지 않습니다.

### Codex 세션 기록은 어떻게 수집되나요?

`~/.codex/sessions/` 폴더에 Codex CLI가 직접 남기는 세션 로그 파일만 읽습니다.
백그라운드 도우미(launchd 데몬 `net.synapse.codex-poller`)가 새 세션이 끝날 때마다
자동으로 정리해 `~/.synapse/private/normalized/codex/`에 저장합니다.

- OpenAI 계정 자격증명이나 API 키는 **읽지 않습니다.**
- Codex CLI를 호출하지도 않습니다 — 이미 끝난 세션의 로컬 파일만 봅니다.
- redact-list 항목과 일반 마스킹 정책이 **Claude 세션과 동일하게** 적용됩니다. 차단된 세션은
  `~/.synapse/private/redaction-reports/`에 기록되고 카드 재료로 쓰이지 않습니다.

Codex를 안 쓰는 분이라면 이 데몬은 단순히 빈 폴더만 polling하므로 영향이 없습니다.

---

## 비용

### 한 달에 얼마나 드나요?

매일 1회 `/synapse-daily` 실행 기준 대략적인 감각입니다.

| 사용 패턴 | 월 추정 비용 (USD) |
|---|---|
| daily만 실행 (변경 거의 없음) | $1~3 |
| daily + 가끔 `/synapse-ask` (주 5회) | $5~10 |
| daily + `/synapse-ask` + `/synapse-resume` (활발히 사용) | $10~20 |
| 매일 `/synapse-resume` 같은 무거운 작업 반복 | $20~40 |

Claude Code 기존 구독·내부 과금 정책에 따라 달라질 수 있습니다.

### 어떤 작업이 비용이 들고 어떤 작업이 무료인가요?

**무료 (내 Mac 안에서만 동작):**

- 데이터 수집 (`collect`)
- 1단계 정규식 마스킹
- 2단계 로컬 AI 마스킹 (apfel)
- 검색 색인 생성 (`rag index`)
- 환경 진단 (`doctor`)

**Claude Code 사용량 발생 (외부 AI 호출):**

- 자료 분류 (`cluster classify`) — 보통 가장 가벼움
- 카드 생성 (`card generate`) — 카드 1장당 한 번
- 질문/회상/결정 (`ask`, `persona what-did-i-think`, `persona decide`)
- 이력서 생성 (`persona draft-resume`)

### 비용을 줄이려면?

1. `--profile-facts-only` 옵션으로 무거운 단계 건너뛰기:
   ```bash
   synapse-memory daily --profile-facts-only
   ```
2. 카드 생성 시 모델을 가볍게:
   ```bash
   synapse-memory card generate --model haiku
   ```
3. 변경이 거의 없는 날은 daily를 건너뛰어도 됩니다 (incremental하게 동작).

---

## 백업과 복구

### 노트북을 분실하거나 초기화하면 어떻게 되나요?

| 데이터 | 위치 | 복구 가능? |
|---|---|---|
| 원본 노트 | Obsidian vault | ✅ iCloud 동기화 시 복구 가능 |
| 요약 카드 | Obsidian vault 내 | ✅ vault 백업하면 함께 복구 |
| Profile · DecisionPatterns | Obsidian vault 내 | ✅ vault 백업하면 함께 복구 |
| L0 원본 사본 | `~/.synapse/private/raw/` | ❌ 다시 만들어야 함 (수집 시 자동 복원) |
| 마스킹된 사본 | `~/.synapse/private/redacted/` | ❌ 다시 만들어야 함 |
| 검색 색인 | `~/.synapse/private/rag/` | ❌ 다시 만들어야 함 (`rag index --rebuild`) |

**결론**: Obsidian vault만 iCloud로 동기화해두면 새 Mac에서 설치 후 daily 1회 실행으로 거의 복원됩니다.

---

## 완전 삭제

### Synapse 관련 모든 데이터를 지우고 싶다면?

```bash
# 1. 처리된 데이터 전부 삭제 (원본 사본 · 마스킹본 · 색인)
rm -rf ~/.synapse

# 2. CLI 도구 제거 (글로벌 설치한 경우)
uv tool uninstall synapse-memory

# 3. 로컬 AI 도구 제거 (선택)
brew uninstall apfel

# 4. 설치 로그 삭제 (선택)
rm -rf ~/Library/Logs/SynapseMemory
```

### Obsidian vault 안의 카드는 어떻게 지우나요?

Obsidian에서 직접 삭제합니다.

- `20_Reference/Projects/*.md` — 프로젝트 카드
- `20_Reference/Companies/*.md` — 회사 카드
- `30_Creative/Drafts/Resume - *.md` — 생성된 이력서 초안
- `90_System/AI/MemoryInbox/*.md` — Profile 후보
- `90_System/AI/Profile.md`, `DecisionPatterns.md` — 승인된 자료

vault 자체를 지우고 싶으면 폴더를 통째로 삭제합니다 (Obsidian 앱과 무관하게 일반 폴더입니다).

---

## 추가 질문

- 보안 모델의 더 정확한 기술 설명: [아키텍처 — Redaction 모델](../architecture.md#redaction-모델)
- 명령별 비용 감각: [usage.md — 비용 감각](../usage.md#비용-감각)
- 모르는 단어가 나오면: [용어집](../glossary.md)
