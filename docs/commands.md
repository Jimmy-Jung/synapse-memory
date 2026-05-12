# CLI 명령 레퍼런스

모든 명령은 저장소 환경을 설치한 뒤 `synapse-memory`로 실행합니다.

```bash
synapse-memory --version
synapse-memory <command> --help
```

## Slash 명령 (Claude Code / Codex)

이 repo는 Claude Code/Codex plugin layer를 포함합니다. plugin이 로드되면 8개 slash 명령이 등록되며, 각각은 내부적으로 위 CLI를 호출합니다.

| Slash | 대응 CLI | 인자 |
|---|---|---|
| `/synapse-ask` | `synapse-memory ask "..."` | `<질의>` |
| `/synapse-recall` | `synapse-memory me what-did-i-think "..."` | `<주제>` |
| `/synapse-decide` | `synapse-memory me decide "..."` | `<상황>` |
| `/synapse-feedback` | `synapse-memory feedback ...` | `last --reject <이유>` 등 |
| `/synapse-cost` | `synapse-memory cost summary ...` | `summary --days 30` 등 |
| `/synapse-resume` | `synapse-memory me draft-resume <slug>` | `<회사 slug>` |
| `/synapse-daily` | `synapse-memory daily [flags]` | (선택) `--profile-facts-only` 등 |
| `/synapse-doctor` | `synapse-memory doctor` | 없음 |

> slash 명령이 CLI를 호출하므로, **`synapse-memory` 바이너리가 PATH에 있어야 합니다**. `uv tool install --editable '.[rag]'` 로 글로벌 설치 권장.

활성화 방법은 [getting-started.md](getting-started.md) 참고. plugin 메타데이터는 `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` 에 정의되어 있습니다.

### 대화형 endpoint TTY 가드

`ask`, `me what-did-i-think`, `me decide`, `me draft-resume`, `me update-profile` 다섯 endpoint 는 사용자가 *터미널에서 직접* 호출했을 때 다음과 같이 동작합니다:

```
$ synapse-memory ask "iOS 클린 아키텍처 어떻게 도입했지?"
⚠  ask 는 LLM 대화 컨텍스트에서 호출할 때 가장 자연스럽게 동작합니다.
   Claude Code / Codex 안에서 `/synapse-ask` 슬래시 명령으로 호출하면
   결과가 대화에 인라인되고 후속 질문에 컨텍스트가 유지됩니다.
   계속 진행하려면 3초 기다리세요. 즉시 우회: SYNAPSE_FROM_AGENT=1
[3초 대기]
[정상 결과 출력]
```

| 조건 | 동작 |
|---|---|
| TTY + env 없음 (= 사람의 직접 호출) | 3초 안내 후 진행 |
| stdout 이 pipe (= 자동화 / 다른 도구) | 즉시 진행, 안내 없음 |
| `SYNAPSE_FROM_AGENT=1` env | 즉시 진행, 안내 없음 |

slash command markdown 은 자동으로 `SYNAPSE_FROM_AGENT=1` 을 설정합니다. 배치 endpoint(`daily`, `doctor`, ...) 는 이 가드를 적용하지 않습니다.

## 자주 쓰는 순서

처음 실행:

```bash
synapse-memory doctor
synapse-memory collect claude-code
synapse-memory collect obsidian
synapse-memory cluster scan
synapse-memory cluster classify --resume
synapse-memory card generate
synapse-memory rag index --rebuild
synapse-memory ask "..."
```

매일 실행:

```bash
synapse-memory daily --profile-facts-only
```

## 환경 진단

### `doctor`

```bash
synapse-memory doctor
```

apfel, Apple Silicon, macOS 버전, L0 디렉터리 권한, Claude Code CLI 상태를 확인합니다. 준비가 끝나면 종료 코드 `0`, 문제가 있으면 `1`을 반환합니다.

## 데이터 수집

### `collect claude-code`

```bash
synapse-memory collect claude-code
synapse-memory collect claude-code --src ~/.claude --dst ~/.synapse/private/raw/claude-code
```

Claude Code의 `projects/*.jsonl`과 `history.jsonl`을 L0 raw 영역으로 증분 mirror합니다.

주요 특징:

- JSONL tail-safe 처리
- offset 메타파일로 재실행 가능
- log rotation 감지 시 다시 mirror

### `collect obsidian`

```bash
synapse-memory collect obsidian
synapse-memory collect obsidian --vault "/path/to/vault"
```

Obsidian vault의 Markdown 파일을 L0 raw 영역으로 증분 mirror합니다.

vault 경로는 환경변수로도 지정할 수 있습니다.

```bash
export SYNAPSE_OBSIDIAN_VAULT="/path/to/vault"
```

기본 제외 대상은 `90_System/AI`, `.obsidian`, `.trash`, `.sync-conflict`입니다.

## Redaction과 평가

### `redact backfill claude-code`

```bash
synapse-memory redact backfill claude-code
synapse-memory redact backfill claude-code --resume
synapse-memory redact backfill claude-code --limit 3 --max-bytes-per-file 50000
```

L0의 Claude Code raw에 Pass 1, Pass 2 redaction을 적용하고 `~/.synapse/private/redacted/` 아래에 저장합니다.

옵션:

| 옵션 | 설명 |
| --- | --- |
| `--limit N` | 처리할 파일 수 제한 |
| `--max-bytes-per-file N` | 파일당 처리할 최대 바이트 |
| `--resume` | 이미 처리된 파일 건너뛰기 |

### `redactlist`

```bash
synapse-memory redactlist show
synapse-memory redactlist add "프로젝트X"
synapse-memory redactlist remove "프로젝트X"
```

NDA 회사명, 프로젝트명, 민감 키워드를 강제로 마스킹하는 목록을 관리합니다. 항목은 대소문자를 구분하지 않고 substring으로 매칭됩니다.

### `eval golden`

```bash
synapse-memory eval golden
synapse-memory eval golden --show-failures 0
synapse-memory eval golden --set tests/golden/pii_synthetic.json
```

PII redaction 골든셋의 precision, recall, F1을 측정합니다. 실제 apfel 호출이 필요합니다.

## Cluster와 Card

### `cluster scan`

```bash
synapse-memory cluster scan
synapse-memory cluster scan --show-details 0
```

수집된 raw에서 같은 프로젝트나 주제로 보이는 묶음을 찾습니다. Claude Code의 cwd와 vault 폴더 구조를 함께 사용합니다.

### `cluster classify`

```bash
synapse-memory cluster classify --resume
synapse-memory cluster classify --limit 10 --model haiku
```

cluster를 `project`, `company`, `domain`, `life`, `skip` 중 하나로 분류하고 결과를 저장합니다.

### `card list`

```bash
synapse-memory card list
synapse-memory card list --type project
synapse-memory card list --type company
```

vault의 `20_Reference/Projects/`, `20_Reference/Companies/`에 있는 Card 목록을 출력합니다.

### `card show`

```bash
synapse-memory card show dansim-ios
synapse-memory card show danggeun --type company
```

Card의 frontmatter와 본문을 출력합니다.

### `card new`

```bash
synapse-memory card new my-project "내 새 프로젝트"
synapse-memory card new acme "Acme Corp" --type company
synapse-memory card new acme "Acme Corp" --type company --force
```

빈 Card 템플릿을 vault에 생성합니다. `--force`는 기존 파일을 덮어씁니다.

### `card generate`

```bash
synapse-memory card generate
synapse-memory card generate --kind project --limit 5
synapse-memory card generate --kind all --model sonnet --force
```

분류된 project/company cluster를 바탕으로 Card 초안을 생성합니다. 기존 Card는 기본적으로 건너뜁니다.

## RAG 검색

### `rag index`

```bash
synapse-memory rag index
synapse-memory rag index --rebuild
```

Card를 임베딩해서 ChromaDB에 저장합니다. `--rebuild`는 기존 collection을 비우고 다시 만듭니다.

### `rag search`

```bash
synapse-memory rag search "iOS retention 회고"
synapse-memory rag search "이력서 프로젝트" --top-k 8 --show-snippet
```

검색 결과 Card를 거리와 함께 출력합니다. 거리가 작을수록 query와 가깝습니다.

feedback loop 가 적용된 Card 는 metadata 의 `feedback_score` 로 거리 보정을 받습니다. reject 된 Card 는 뒤로 밀리고 accept 된 Card 는 같은 cosine 거리에서 앞으로 당겨집니다.

## 피드백 루프

### `feedback`

```bash
synapse-memory feedback last --reject "관련 없음"
synapse-memory feedback last --accept
synapse-memory feedback card dansim-ios --reject "SwiftUI 주제에는 부적합"
synapse-memory feedback card dansim-ios --accept
synapse-memory feedback pattern pattern-b330dfadf791 --weight -0.3
```

AI 답변이나 Card/DecisionPattern 에 사용자 피드백을 남깁니다. `feedback` 은 batch endpoint 이며 외부 LLM 을 호출하지 않습니다.

| 대상 | 용도 |
|---|---|
| `last` | 직전 `ask` / `me what-did-i-think` / `me decide` 답변의 citation 대상에 피드백 |
| `card <id>` | 특정 ProjectCard 또는 CompanyCard 에 직접 피드백 |
| `pattern <id>` | 특정 DecisionPattern 에 직접 weight 조정 |

| 옵션 | 동작 |
|---|---|
| `--accept` | 긍정 신호, 기본 `+0.20` |
| `--reject <reason>` | 부정 신호, 기본 `-0.30`; reason 필수 |
| `--weight <delta>` | 직접 가중치 조정, 범위 `-1.0`~`1.0` |

직전 답변 대상이 없으면 event 를 기록하지 않고 `No recent answer found. Run ask/me first, then retry feedback last.` 를 출력합니다. feedback event 는 `~/.synapse/private/feedback.jsonl` 에 append-only 로 저장되며, 다음 `rag index` 이후 Card 검색 가중치로 반영됩니다.

## 비용 관측

### `cost summary`

```bash
synapse-memory cost summary
synapse-memory cost summary --days 7 --by command
synapse-memory cost summary --days 30 --by model --json
```

Claude Code CLI 와 apfel 외부 호출이 남긴 `~/.synapse/private/cost.jsonl` 을 최근 N일 기준으로 집계합니다. `cost` 는 batch endpoint 이며 외부 LLM 을 호출하지 않습니다.

| 옵션 | 기본값 | 동작 |
|---|---:|---|
| `--days N` | `30` | 최근 N일 event 만 포함 |
| `--by command\|model` | `command` | command 또는 model 기준 그룹화 |
| `--json` | off | 표 대신 JSON 출력 |

로그가 없거나 기간 내 event 가 없으면 exit 0 으로 `데이터 없음 — 아직 기록된 cost event 가 없습니다.` 를 출력합니다. cost event 는 prompt/response 원문을 저장하지 않고 command, provider, model, token count, usd, elapsed, status 같은 metadata 만 저장합니다.

## 사용자 endpoint

### `ask`

```bash
synapse-memory ask "내가 클린 아키텍처를 어떻게 도입했지?"
synapse-memory ask "어떤 회사에 관심 있었지?" --kind company
synapse-memory ask "기술 스택 정리" --top-k 8 --model sonnet
```

자연어 질문을 받고, 관련 Card를 검색한 뒤 Claude로 답변을 합성합니다.

### `me generate <recipe>` (007-me-recipes)

```bash
synapse-memory me generate weekly_report --input period=2026-W19
synapse-memory me generate journal --input date=2026-05-12
synapse-memory me generate brainstorm --input topic="시간관리"
synapse-memory me generate resume --input company_id=danggeun --language en
```

Recipe markdown 기반 generator. 빌트인 6종 (`resume` / `weekly_report` / `journal` /
`brainstorm` / `decide` / `recall`) + 사용자 vault `90_System/AI/recipes/` 에 추가한
markdown 도 자동 발견. 5분 워크스루는 [quickstart.md](../specs/007-me-recipes/quickstart.md) 참고.

### `me recipes list` · `me recipes show <recipe>`

```bash
synapse-memory me recipes list                # builtin + user recipe 표
synapse-memory me recipes list --json         # machine-readable envelope
synapse-memory me recipes show weekly_report  # input_schema·rag_filter·system_prompt preview
```

### `me draft-resume`

```bash
synapse-memory me draft-resume danggeun
synapse-memory me draft-resume danggeun --top-k 6 --model sonnet
```

CompanyCard와 매칭되는 ProjectCard를 바탕으로 회사 맞춤 이력서 초안을 vault에 작성합니다.
007-me-recipes 도입 이후 내부적으로는 `me generate resume --input company_id=…` 와
동일한 generator pipeline 을 사용하지만 외부 stdout / exit code / 저장 경로는 보존됩니다.

### `me what-did-i-think`

```bash
synapse-memory me what-did-i-think "TCA 아키텍처"
synapse-memory me what-did-i-think "AI 코딩 도구 사용 경험" --top-k 8
synapse-memory me what-did-i-think "클린 아키텍처" --timeline
synapse-memory me what-did-i-think "이직 고민" --by time --limit 10
```

특정 주제에 대해 과거 자료를 검색하고, 시간순 변화와 현재 입장을 요약합니다.

**정렬 모드** (FR-A1, v0.5):

| 옵션 | 동작 | 외부 LLM 호출 |
|---|---|---|
| (기본 / `--by distance`) | cosine 유사도 + Claude 가 시간순 변화·일관성 정리 | ✓ |
| `--timeline` / `--by time` | period_end 내림차순 + 분기·월 그룹 헤더로 로컬 포맷 | ✗ |
| `--limit N` | 출력 카드 최대 수 (기본 20, 범위 1~100) | — |

`--timeline` 과 `--by distance` 가 동시 지정되면 `error: ... conflict — pick one.` 메시지와 함께 exit 1 입니다.

ProjectCard 의 `period_end` 가 없으면: `status=active` → 오늘 날짜로 폴백 ("(오늘 YYYY-MM-DD)" 라벨), 그 외 → `created` 폴백 ("(created)" 라벨). CompanyCard 는 `last_reviewed` 가 정렬 키 ("(last reviewed)" 라벨).

### `me decide`

```bash
synapse-memory me decide "다음 분기에 어디에 시간을 투자할까?"
```

Profile, DecisionPatterns, RAG 검색 결과를 함께 사용해 의사결정 초안을 제안합니다.

### `me update-profile`

```bash
synapse-memory me update-profile
synapse-memory me update-profile --facts-only --sample-lines 200
```

최근 raw 활동에서 ProfileFact와 DecisionPattern 후보를 추출해 `90_System/AI/MemoryInbox/`에 작성합니다.

## 일일 통합 파이프라인

### `daily`

```bash
synapse-memory daily
synapse-memory daily --profile-facts-only
synapse-memory daily --dry-run
```

가능한 단계는 다음과 같습니다.

```text
collect_claude_code
collect_obsidian
classify
generate
index
update_profile
```

특정 단계만 실행하거나 제외할 수 있습니다.

```bash
synapse-memory daily --only collect_obsidian,index
synapse-memory daily --skip update_profile
```

모델 관련 옵션:

```bash
synapse-memory daily \
  --classify-model haiku \
  --generate-model sonnet \
  --profile-model sonnet \
  --profile-sample-lines 200
```

## 빠른 문제 해결

| 상황 | 해결 |
| --- | --- |
| `결과 없음` | `synapse-memory rag index --rebuild` |
| `분류 결과 없음` | `synapse-memory cluster classify --resume` |
| vault 경로 없음 | `SYNAPSE_OBSIDIAN_VAULT` 또는 `--vault` 지정 |
| Claude 사용 불가 | `claude --version`, 로그인 상태 확인 |
| apfel 사용 불가 | `synapse-memory doctor`, apfel 설치 확인 |
