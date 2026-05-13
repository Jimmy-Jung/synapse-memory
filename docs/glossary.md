# 용어집

> Synapse Memory 문서에서 자주 나오는 용어를 한 곳에 정리합니다.
> 비개발자도 이해할 수 있는 설명 → 더 정확한 기술 정의 순으로 적습니다.

## 어떤 카테고리에 어느 절을 보면 되나

| 카테고리 | 어디 |
|---|---|
| "Vault·Card·Profile·Cluster·RAG 같은 핵심 개념" | [§ 핵심 개념](#핵심-개념) |
| "내 노트 어느 폴더에 둬야 하나 (00_Inbox / 10_Active / …)" | [§ Vault 폴더 컨벤션](#vault-폴더-컨벤션) |
| "L0~L3 · Redaction · redact-list" | [§ 보안 모델](#보안-모델) |
| "apfel · Claude Code · 두 AI 비교" | [§ 도구](#도구) |
| "슬래시 명령 / 배치 명령 / TTY 가드" | [§ 명령](#명령) |
| "Collect · Classify · Generate · Index · Update Profile 단계" | [§ 데이터 흐름](#데이터-흐름) |
| "Dense · BM25 · Hybrid 검색" | [§ 검색 모드](#검색-모드) |
| "mirror · incremental · frontmatter · embedding · chunk · upsert · atomic write · NFC · PARA/Johnny.Decimal" | [§ 기술 용어](#기술-용어) |

## 핵심 개념

### Vault (볼트)

**쉬운 설명**: 내가 평소 쓰는 Obsidian 노트 폴더 전체.

**기술 정의**: Obsidian이 관리하는 마크다운 파일들의 최상위 폴더. `SYNAPSE_OBSIDIAN_VAULT` 환경변수 또는 설치 시 GUI에서 지정.

### Vault 폴더 컨벤션

[PARA](https://fortelabs.com/blog/para/) 변형 — 각 폴더는 누가 만들고 Synapse가 어떻게 다루는지가 다릅니다. 자세한 표·워크플로는 [usage.md의 vault 폴더 컨벤션](usage.md#vault-폴더-컨벤션--노트를-어디에-두면-카드가-생기나) 참고.

#### `00_Inbox/`

**쉬운 설명**: 정리 안 된 새 노트를 부담 없이 던지는 임시 받은편지함.

**기술 정의**: PARA의 Inbox와 동일 의미. Synapse는 특별 처리 없이 일반 mirror만 수행 — cluster 식별 신호가 약해 **자동 Card 생성에는 잘 잡히지 않습니다.** 정리 시 `10_Active/<회사>/<프로젝트>/`로 옮기는 흐름을 권장.

#### `10_Active/<회사>/<프로젝트>/`

**쉬운 설명**: 진행 중 프로젝트 노트를 두는 곳.

**기술 정의**: **Synapse cluster 식별의 주된 소스.** 폴더 segment(NFC 정규화 후)가 cluster_id로 변환되어 같은 폴더에 노트 2개 이상이 쌓이면 cluster 후보가 됩니다.

#### `20_Reference/{Projects,Companies}/`

**쉬운 설명**: Synapse가 만든 요약 카드 저장소.

**기술 정의**: `card generate` 단계의 출력. ProjectCard/CompanyCard frontmatter + 본문. 자동 생성 시 `status: draft`, 사용자가 승격하면 `active`.

#### `30_Creative/Drafts/`

**쉬운 설명**: Synapse가 만든 이력서 초안 저장소.

**기술 정의**: `persona draft-resume` 명령의 출력 위치. 파일명 형식 `Resume - <회사> (YYYY-MM).md`.

#### `90_System/AI/`

**쉬운 설명**: Synapse 전용 시스템 폴더 — 사용자는 읽고 승격만, 직접 작성 금지.

**기술 정의**: `MemoryInbox/`, `Profile.md`, `DecisionPatterns.md`, `DailyReports/YYYY-MM-DD.md`, `recipes/` 보관. obsidian collector의 기본 제외 대상(commands.md:123).

### Card (카드)

**쉬운 설명**: 프로젝트나 회사를 한 장으로 요약한 마크다운 문서.

**기술 정의**: ProjectCard / CompanyCard 형식의 frontmatter + 본문 마크다운. 위치는 vault 안 `20_Reference/Projects/`, `20_Reference/Companies/`. 자동 생성 시 `status: draft`, 사용자가 검토하면 `status: active`.

### ProfileFact (프로필 사실)

**쉬운 설명**: "이 사람은 ~한 사람이다" 한 줄짜리 메모.

**기술 정의**: `persona decide`·`persona design-project`·`persona draft-resume` 등이 의사결정·생성 컨텍스트로 사용. `90_System/AI/Profile.md`에서 승인됨. 카테고리: `work_style`, `preference`, `strength`, `weakness`, `tech`, `interest`, `workflow`, `value`, `voice` (총 9개).

### voice 카테고리 🆕

**쉬운 설명**: "이 사람은 이런 말투·문장 길이·표현 선호를 가진다" 사실.

**기술 정의**: ProfileFact 의 9번째 카테고리. 외부 자료 (`persona ingest`) 흡수로 가장 잘 추출되며, claude history 만으로는 추출이 빈약함. `persona design-project` 의 결과 톤 결정에 직접 사용.

### DecisionPattern (의사결정 패턴)

**쉬운 설명**: "이 사람은 ~할 때 ~하게 결정한다" 한 줄짜리 메모.

**기술 정의**: 과거 결정에서 추출한 if-then 형식의 패턴. `90_System/AI/DecisionPatterns.md`에서 승인됨.

### MemoryInbox (메모리 인박스)

**쉬운 설명**: AI가 만든 "이 사람 이런 것 같다" 후보 메모함. 내가 검토해서 Profile로 옮기는 작업 공간.

**기술 정의**: `90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md` — `daily --profile-facts-only`가 매일 자동 추가.

### Cluster (클러스터)

**쉬운 설명**: "같은 프로젝트나 회사로 묶을 수 있는 자료 조각" 묶음.

**기술 정의**: Claude Code session의 cwd 또는 Obsidian 폴더 segment로 식별. NFC 정규화 적용.

### RAG (Retrieval-Augmented Generation)

**쉬운 설명**: "관련 자료를 찾아서 그것만 보고 답하기" 방식. AI가 환각(없는 사실 지어내기)을 줄임.

**기술 정의**: 질의 → 벡터 검색 → 매칭된 카드 → LLM 프롬프트에 인용으로 주입.

---

## 보안 모델

### L0 / L1 / L2 / L3 (4단계 메모리 모델)

| 계층 | 별칭 | 위치 | 외부 노출 |
|---|---|---|---|
| L0 | 원본 (raw) | `~/.synapse/private/raw/` (권한 0700) | ❌ 절대 안 됨 |
| L1 | 마스킹본 (redacted) | `~/.synapse/private/redacted/` | ✅ 가능 |
| L2 | 진실원본 (truth source) | Obsidian vault 안 (사용자 승인 카드) | ✅ 검색 재료 |
| L3 | 검색 색인 (index) | `~/.synapse/private/rag/chroma/` | ❌ 색인 자체 안 나감 |

### Redaction (마스킹)

**쉬운 설명**: 민감정보를 가리는 작업.

**기술 정의**: 2-pass 마스킹.

- **Pass 1**: 정규식 + Luhn 체크 — 이메일, 한국 전화, 신용카드, 주민번호, IPv4, JWT, AWS/API 키, Bearer 토큰, redact-list.
- **Pass 2**: 로컬 LLM(apfel) — 사람·조직·주소·민감주제·secret. 내 Mac 안에서만 실행.

### redact-list (리덕트 리스트)

**쉬운 설명**: "이 단어는 무조건 가려라" 사용자 정의 목록.

**기술 정의**: `~/.synapse/private/.redactlist`. `synapse-memory redactlist add "..."`로 추가.

---

## 도구

### apfel

**쉬운 설명**: 내 Mac 안에서만 동작하는 로컬 AI. 마스킹 2단계와 짧은 분류에 사용.

**기술 정의**: Apple FoundationModels 기반 CLI. [apfel.franzai.com](https://apfel.franzai.com). Apple Silicon 전용.

### Claude Code (CLI)

**쉬운 설명**: Anthropic의 공식 코딩 도우미. Synapse는 이걸 외부 AI로 호출.

**기술 정의**: subprocess로 호출, 기존 OAuth 인증 사용, 별도 API 키 발급 불필요. `system_prompt` 명시 주입.

### apfel vs Claude Code

| 구분 | apfel | Claude Code |
|---|---|---|
| 실행 위치 | 내 Mac 안 | 외부 클라우드 |
| 입력 | 원본 가능 | 마스킹본/카드만 |
| 용도 | 마스킹 · 분류 | 카드 생성 · 답변 · 이력서 |

---

## 명령

### Slash 명령 (Claude Code / Codex 안에서)

| Slash | 대응 CLI | 설명 |
|---|---|---|
| `/synapse-onboard` | (대화형 스크립트) | 최초 사용자 인도 — 답답함 1개 끝까지 체험 |
| `/synapse-assistant` | `assistant-status` + 대화 | 일상 비서 — 추천 + 동의 시 대신 실행 (cleanup 후보도 추천) |
| `/synapse-cleanup` | `cleanup scan` / `cleanup apply` | vault 청소 — 오래된·휴면·빈 자료를 archive로 이동 |
| `/synapse-config` | `config show/get/set/edit/reset/validate` | 사용자 설정 — `~/.synapse/config.yaml` 자연어 변경 |
| `/synapse-ask` | `ask` | 자연어 질의 |
| `/synapse-recall` | `persona what-did-i-think` | 시간순 회상 |
| `/synapse-decide` | `persona decide` | 의사결정 코파일럿 |
| `/synapse-resume` | `persona draft-resume` | 회사 맞춤 이력서 |
| `/synapse-daily` | `daily` | 일일 통합 파이프라인 |
| `/synapse-doctor` | `doctor` | 환경 진단 |
| `/synapse-fix` | `doctor --fix` | 환경 자동 복구 |
| `/synapse-feedback` | `feedback` | 카드 평가 (accept/reject) |
| `/synapse-cost` | `cost summary` | 비용 요약 (예정) |

### 배치 명령 (자동화·유지보수)

`daily`, `doctor`, `collect`, `cluster`, `card`, `rag`, `redact`, `eval` — 사람·cron·LaunchAgent에서 자유롭게 호출.

### 대화형 endpoint TTY 가드

**쉬운 설명**: `ask`, `me *` 명령을 *터미널에서 직접* 부르면 3초 안내가 나옵니다. Claude Code의 슬래시 명령으로 부르라는 권장 안내입니다.

**기술 정의**: stdout이 TTY이고 `SYNAPSE_FROM_AGENT=1` 환경변수가 없으면 3초 대기 후 진행. slash command markdown은 자동으로 이 env를 설정합니다.

---

## 데이터 흐름

### Collect (수집)

`collect claude-code`, `collect obsidian` — 외부 소스를 L0 raw로 증분 mirror.

### Classify (분류)

`cluster scan` → `cluster classify` — raw 조각을 프로젝트/회사 후보로 묶음.

### Generate (카드 생성)

`card generate` — Cluster를 LLM으로 한 장짜리 카드(L2)로 요약.

### Index (색인)

`rag index` — 카드를 bge-m3 임베딩 + ChromaDB(L3)에 upsert. `--include-raw`로 BM25 sidecar 포함.

### Update Profile (프로필 업데이트)

`persona update-profile` — claude history 에서 ProfileFact 후보 추출 → MemoryInbox에 작성.

### Ingest (외부 자료 흡수) 🆕

`persona ingest --file <path>` — vault 밖 markdown / txt 파일 (회고록 · 일기 · 기획서 초안 등) 흡수. raw 는 `~/.synapse/private/raw/persona/` 에 0600 으로 mirror, redacted 텍스트로 ProfileFact 후보 추출 → MemoryInbox 같은 PR 에 append. `voice` 카테고리 보강에 핵심.

### Design Project (프로젝트 설계 초안) 🆕

`persona design-project "<아이디어>"` — Profile (`tech`/`work_style`/`voice`) + DecisionPatterns + ProjectCard RAG 종합 → 사용자 스타일이 반영된 설계 markdown 을 `20_Projects/Drafts/` 에 저장. system prompt 가 `[Profile: <category>]` 인용 + 비사용 프레임워크 금지 규칙 강제.

---

## 검색 모드

### Dense (밀집 벡터)

**쉬운 설명**: 의미가 비슷한 카드를 찾기. 표현이 달라도 매칭 가능.

**기술 정의**: bge-m3 임베딩 + ChromaDB cosine similarity.

### BM25 (키워드)

**쉬운 설명**: 정확한 단어가 들어 있는 카드를 찾기. 회사명·사람 이름 같은 고유명사에 강함.

**기술 정의**: rank-bm25 사용. `rag index --include-raw`로 색인 필요.

### Hybrid (혼합)

**쉬운 설명**: Dense + BM25 결과를 합쳐서 둘 다의 장점 활용.

**기술 정의**: Reciprocal Rank Fusion (RRF, k=60). recipe frontmatter `rag_mode: hybrid` 또는 `--rag-mode hybrid`로 활성화.

---

## 기술 용어

문서 곳곳에 등장하는 짧은 전문 용어를 한 곳에 모았습니다. *이게 뭐였더라* 싶을 때 여기를 보세요.

### mirror (미러)

**쉬운 설명**: 원본 폴더와 똑같이 *그대로 복사해두는* 사본. 원본이 바뀌면 *바뀐 부분만* 따라잡습니다.

**기술 정의**: Synapse의 `collect_*` 단계는 incremental mirror — 이미 복사한 파일은 mtime·hash로 비교해 건너뛰고, 새/변경된 부분만 `~/.synapse/private/raw/`에 복제합니다. 원본 파일은 절대 수정되지 않습니다.

### incremental (증분)

**쉬운 설명**: *전체*가 아니라 *바뀐 것만* 처리하는 방식. 매일 다시 돌려도 빠른 이유.

**기술 정의**: 각 단계가 offset/hash/exists 검사로 이미 처리된 항목을 건너뜀. 그래서 두 번째 `daily`부터는 5분 안에 끝남.

### frontmatter (프론트매터)

**쉬운 설명**: 마크다운 파일 맨 위에 `---`로 감싼 메타데이터 블록. Obsidian의 태그·상태 정보가 여기 들어갑니다.

**기술 정의**: YAML 형식. Synapse는 Card의 `status`, `kind`, `aliases` 등을 frontmatter로 관리. 예시는 [Card 항목](#card-카드) 참고.

### embedding (임베딩)

**쉬운 설명**: 글의 *의미*를 숫자 배열(벡터)로 바꾸는 것. 단어가 달라도 의미가 비슷하면 벡터가 가까워져서 검색이 됩니다.

**기술 정의**: Synapse는 [bge-m3](https://huggingface.co/BAAI/bge-m3) 모델로 카드를 ~1024차원 벡터로 변환해 ChromaDB에 저장. Dense 검색의 기반.

### chunk (청크)

**쉬운 설명**: 긴 글을 검색 단위로 자른 *작은 토막*.

**기술 정의**: `rag index --include-raw`가 raw markdown을 ~500토큰 단위로 분할해 청크별로 임베딩. 기본 모드는 카드 전체를 1 청크로 다룸.

### upsert (업서트)

**쉬운 설명**: 같은 항목이 이미 있으면 *덮어쓰고*, 없으면 *새로 만드는* 한 가지 동작.

**기술 정의**: update + insert 합성어. `rag index`가 같은 ID의 카드는 새 임베딩으로 교체하고, 새 ID는 신규 삽입.

### atomic write (원자적 쓰기)

**쉬운 설명**: 파일을 *완전히 다 쓴 다음에* 한 번에 갈아끼우기. 도중에 누가 읽어도 *반쪽짜리* 파일을 절대 보지 못함.

**기술 정의**: 임시 파일에 전체 내용 작성 → `os.replace()`로 원자적 rename. `daily.status.json` 같은 동시 접근 파일에 사용.

### NFC 정규화 (NFC normalization)

**쉬운 설명**: 한글이 자모 분리된 채로 저장된 파일명(macOS 기본)을 *합쳐진 형태*로 통일. 같은 "가나다"가 두 가지로 저장돼 매칭 안 되는 문제 방지.

**기술 정의**: Unicode NFC (Normalization Form Canonical Composition). Obsidian collector와 cluster 식별이 모든 경로·파일명에 적용.

### PARA / Johnny.Decimal

**쉬운 설명**: Synapse가 가정하는 vault 폴더 구조의 *출처 두 가지*.

- **PARA** — Obsidian/Notion 표준 폴더 분류 (**P**rojects · **A**reas · **R**esources · **A**rchives)
- **Johnny.Decimal** — 모든 폴더에 두 자리 숫자 prefix를 붙이는 시스템

이 둘을 섞어서 `00_Inbox` / `10_Active` / `20_Reference` / `30_Creative` / `90_System` 구조가 됩니다.

**기술 정의**: [Tiago Forte의 PARA Method](https://fortelabs.com/blog/para/) + [Johnny.Decimal](https://johnnydecimal.com/) 하이브리드. *왜 이 변형을 골랐는지*는 [설계 개요](for-everyone/architecture-overview.md#왜-이런-폴더-구조00_inbox-10_active--를-골랐나요), *각 폴더별 용도·동작*은 [Vault 폴더 컨벤션](#vault-폴더-컨벤션) 참고.

### ChromaDB

**쉬운 설명**: 임베딩(벡터)을 저장하고 *비슷한 것* 찾기에 특화된 작은 DB. 내 Mac 안에서만 동작.

**기술 정의**: 오픈소스 vector store. 위치는 `~/.synapse/private/rag/chroma/`. cosine similarity로 nearest neighbor 검색.

### RRF (Reciprocal Rank Fusion)

**쉬운 설명**: 두 가지 검색 결과(의미 검색 + 키워드 검색)를 합치는 점수 공식. 양쪽에서 상위에 잡힌 카드를 더 높이 평가.

**기술 정의**: `score = Σ 1/(k + rank_i)`, k=60. Hybrid 모드의 결합 방식.

### subprocess

**쉬운 설명**: 한 프로그램이 *다른 프로그램*을 따로 띄워서 호출하는 방식.

**기술 정의**: Synapse는 Claude Code/Codex/apfel CLI를 Python `subprocess`로 호출 — 직접 SDK 키를 들고 다니지 않고, 사용자의 기존 CLI 인증을 그대로 활용.

### launchd

**쉬운 설명**: macOS의 *상시 도우미 관리자*. 시스템 시작 시·주기적으로 백그라운드 프로그램을 자동 실행시킴.

**기술 정의**: Apple의 init/service manager. Synapse는 `net.synapse.codex-poller`를 LaunchAgent(`~/Library/LaunchAgents/*.plist`)로 등록해 Codex 세션을 상시 polling.

### polling (폴링)

**쉬운 설명**: *주기적으로 확인하기*. "새 게 있나?" 일정 간격으로 들여다보는 방식.

**기술 정의**: 이벤트 push 대신 일정 시간마다 상태를 조회. 예: `synapse-memory daily-status --watch`가 2초 간격으로 status JSON 조회.

---

## 기타

### Recipe

**쉬운 설명**: "이력서를 어떻게 만들지" 같은 작업 명세를 마크다운으로 적은 것.

**기술 정의**: `src/synapse_memory/recipes/` 또는 사용자 vault의 markdown frontmatter + 본문. `persona generate <recipe>`로 실행.

### Daily 파이프라인

`/synapse-daily` 한 줄이 다음 단계를 묶어서 실행: collect → classify → generate → index → update_profile.

### LaunchAgent

**쉬운 설명**: macOS에서 매일 자동 실행하도록 등록하는 설정.

**기술 정의**: `~/Library/LaunchAgents/*.plist` — Synapse는 향후 `synapse-memory install-agent` 명령으로 자동 등록 예정 (backlog).

---

## 더 알아보기

- [동작 원리 (비유 기반)](for-everyone/how-it-works.md)
- [아키텍처 (기술 정확)](architecture.md)
- [CLI 레퍼런스](commands.md)
