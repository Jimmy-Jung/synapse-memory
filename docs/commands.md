# CLI 명령 레퍼런스

## 환경 / 데이터 수집

### `doctor`

```bash
synapse-memory doctor
```

환경 진단 + L0 setup. 매 호출마다:
- apfel 설치 + 버전
- Apple Silicon (arm64)
- macOS 26+ (Tahoe)
- L0 디렉토리 0700 강제
- Claude Code CLI 설치 + 버전

종료 코드: 모두 ✓면 0, 미충족이면 1.

### `collect claude-code`

```bash
synapse-memory collect claude-code
  --src PATH     # ~/.claude (기본)
  --dst PATH     # ~/.synapse/private/raw/claude-code (기본)
```

`~/.claude/projects/<slug>/<id>.jsonl` + `~/.claude/history.jsonl`을 L0로 incremental mirror.

특징:
- jsonl tail-safe (partial line 보호)
- offset 메타파일로 재시작 idempotent
- rotation 감지 시 처음부터 재mirror

### `collect obsidian`

```bash
synapse-memory collect obsidian
  --vault PATH   # iCloud Obsidian 경로 (기본)
  --dst PATH     # ~/.synapse/private/raw/obsidian (기본)
```

`SYNAPSE_OBSIDIAN_VAULT` 환경변수로도 vault 위치 지정 가능.

특징:
- mtime + size + sha256 3-tier 변경 감지
- 90_System/AI, .obsidian, .trash, .sync-conflict 자동 제외
- 한국어 파일명 (NFD/NFC) 정상 처리

## Redaction

### `redact backfill claude-code`

```bash
synapse-memory redact backfill claude-code
  --limit N             # 처리할 파일 수
  --max-bytes-per-file N  # 파일당 처리 최대 바이트 (샘플링용)
  --resume              # 이미 redact된 파일 skip
```

L0 raw 전체에 Pass 1+2 적용 → `redacted/` 저장. 1 파일당 분 단위 소요.

### `redactlist show / add / remove`

```bash
synapse-memory redactlist show
synapse-memory redactlist add "프로젝트X"
synapse-memory redactlist remove "프로젝트X"
```

NDA 회사·프로젝트 키워드를 모든 raw에서 강제 `[REDACT_*]` 마스킹. Pass 1 단계에 동적 합류 (priority 200).

### `eval golden`

```bash
synapse-memory eval golden
  --set PATH           # 골든셋 JSON 파일 (기본 tests/golden/pii_synthetic.json)
  --show-failures N    # 실패 sample N개 출력 (0=숨김)
```

골든셋 P/R/F1 측정. 현재 골든셋: 58 samples, OVERALL F1=0.92.

## Card / Cluster

### `cluster scan`

```bash
synapse-memory cluster scan
  --show-details N   # 상위 N 클러스터 상세 출력 (0=요약만)
```

raw에서 프로젝트 클러스터 식별. Claude Code cwd + vault 폴더 segment 기반.

### `cluster classify`

```bash
synapse-memory cluster classify
  --limit N
  --resume        # 이미 분류된 cluster skip
  --model MODEL   # haiku (기본) / sonnet / opus
```

각 cluster → `project | company | domain | life | skip` 분류. haiku로 ~$0.001/cluster.

결과: `~/.synapse/private/clusters/classifications.json`.

### `card list`

```bash
synapse-memory card list
  --type project|company|all   # 기본 all
```

vault `20_Reference/{Projects,Companies}/`에 있는 Card 목록.

### `card show <id>`

```bash
synapse-memory card show dansim-ios
synapse-memory card show 메가스터디 --type company
```

Card 내용 출력 (yaml frontmatter + body).

### `card new <id> <name>`

```bash
synapse-memory card new my-project "내 새 프로젝트"
synapse-memory card new acme "Acme Corp" --type company
synapse-memory card new x "X" --force   # 기존 덮어쓰기
```

빈 Card 템플릿 생성 (사용자가 vault에서 편집).

### `card generate`

```bash
synapse-memory card generate
  --kind project|company|all   # 기본 all
  --limit N
  --model sonnet               # sonnet 권장 (yaml 안정성)
  --force                      # 기존 Card 덮어쓰기
```

classify된 project/company cluster를 Claude로 Card 자동 생성. ~$0.3/Card.

## RAG / 검색

### `rag index`

```bash
synapse-memory rag index
  --rebuild   # collection 비우고 처음부터
```

모든 Card를 bge-m3로 임베드 → ChromaDB upsert. 첫 호출 시 bge-m3 ~2.3GB 다운로드.

### `rag search`

```bash
synapse-memory rag search "iOS retention 회고"
  --top-k 5
  --show-snippet
```

dense vector 검색 (cosine 유사도). 거리 낮을수록 가까움.

## Endpoint (사용자 가치)

### `ask`

```bash
synapse-memory ask "내가 클린 아키텍처 어떻게 도입했지?"
  --top-k 5
  --model sonnet
  --kind project|company   # 특정 종류만 retrieve
```

자연어 질의 → RAG retrieve + Claude 합성 답변. 출처 인용 `[card_id]`.

비용: sonnet ~$0.10/call, haiku ~$0.03/call.

### `me draft-resume`

```bash
synapse-memory me draft-resume danggeun
  --top-k 6      # 매칭할 ProjectCard 수
  --model sonnet
```

CompanyCard + 매칭 ProjectCard들 → 회사 맞춤 이력서 → vault `30_Creative/Drafts/Resume - <회사> (YYYY-MM).md`.

비용: sonnet ~$0.3/이력서.

### `me what-did-i-think`

```bash
synapse-memory me what-did-i-think "TCA 아키텍처"
  --top-k 8
  --model sonnet
```

주제에 대한 과거 사고 회상 (시간순 / 입장별 정리).

### `me decide`

```bash
synapse-memory me decide "이력서를 sonnet으로 갈지 opus로 갈지"
  --top-k 6
  --model sonnet
```

vault `90_System/AI/Profile.md` + `DecisionPatterns.md` + RAG search → 의사결정 추천.

출력에 `(Profile/Patterns 사용 ✓)` 보이면 진짜 클론 모드 동작.
`(Profile 없음 — 일반 모드)`면 `me update-profile` 먼저 + 검토 후 진실원본 promote 필요.

### `me update-profile`

```bash
synapse-memory me update-profile
  --sample-lines 200   # history.jsonl 마지막 N 줄
  --model sonnet
  --facts-only         # DecisionPattern 추출 skip (비용 절감)
```

L0 raw → Claude 분석 → `90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md` PR 생성.

검토 후 사용자가 좋은 항목을 `Profile.md`, `DecisionPatterns.md`에 복사.

## 일일 통합

### `daily`

```bash
synapse-memory daily
  --only STEP1,STEP2          # 특정 단계만
  --skip STEP                  # 제외할 단계
  --classify-model haiku
  --generate-model sonnet
  --profile-model sonnet
  --profile-sample-lines 200
  --profile-facts-only         # DecisionPattern skip
  --dry-run                    # 단계만 출력, 실행 X
```

통합 파이프라인. 가능한 단계:
- `collect_claude_code`
- `collect_obsidian`
- `classify`
- `generate`
- `index`
- `update_profile`

매일 5분 워크플로 권장:

```bash
synapse-memory daily --profile-facts-only
```

비용 절감 (모두 haiku):
```bash
synapse-memory daily \
  --classify-model haiku \
  --generate-model haiku \
  --profile-model haiku \
  --profile-facts-only
```

## 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 성공 |
| 1 | 실행 중 일부 실패 (continued) |
| 2 | 환경 미충족 (사전 조건 안 됨) |

## 환경변수

| 변수 | 용도 |
|---|---|
| `SYNAPSE_L0_ROOT` | L0 위치 override (기본 `~/.synapse/private`) |
| `SYNAPSE_OBSIDIAN_VAULT` | vault 경로 override |
| `HF_TOKEN` | HuggingFace 토큰 (bge-m3 다운로드 속도) |

## 빈 출력 시 디버깅

```bash
synapse-memory doctor                          # 환경 확인
ls ~/.synapse/private/raw/                     # 수집된 게 있는지
ls $VAULT/20_Reference/Projects/               # Card 있는지
python -c "from synapse_memory.rag import open_vector_store; print(open_vector_store().count())"
```
