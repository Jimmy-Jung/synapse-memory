# Synapse Memory v2

> 개인용 AI 비서 / 세컨드 브레인 / 클론 — vault 데이터 위에서 동작하는 RAG + 자동 메모리 시스템.

Obsidian vault와 Claude Code 활동 로그를 안전하게 mirror·redact한 뒤,
자동으로 Project / Company Card를 추출하고 회사별 맞춤 이력서를 합성하고
주제 회상 / 의사결정 코파일럿까지 동작하는 로컬-first 도구입니다.

- **AI 비서**: 자연어 질의 → RAG 검색 → 출처 인용 답변
- **세컨드 브레인**: 시간순 사고 회상, "내가 X에 대해 뭐라 했었지?"
- **내 클론**: vault Profile.md + DecisionPatterns.md 기반 의사결정 추천
- **일일 5분 워크플로**: `synapse-memory daily` 한 줄로 모든 단계 incremental 실행

## 동작 화면

```bash
$ synapse-memory ask "iOS 클린 아키텍처 어떻게 도입했지?"
**Domain–Data–Presentation 3계층 분리 + Repository 패턴 + DIContainer 조합으로 도입했습니다.**

구체적인 접근 순서: [이력서-2026]
1. Domain–Data–Presentation 계층 분리
2. Repository 패턴
3. DIContainer

도입 기간 2024.01~05, Tuist 멀티 모듈화로 확장.
결과: 버그 수정 시간 71% 단축, 크래시율 2.1% → 0.8%.
```

```bash
$ synapse-memory me draft-resume danggeun
✓ 이력서 생성: ~/.../30_Creative/Drafts/Resume - 당근마켓 (2026-05).md
  매칭 ProjectCard: dansim-ios, 이력서-2026, mobile-ios-slc-tablet ...
```

## 시스템 요구사항

| 항목 | 요구 |
|---|---|
| 하드웨어 | Apple Silicon (M1 이상) |
| OS | macOS Tahoe 26.0+ |
| Python | 3.11+ |
| 외부 도구 | [apfel](https://apfel.franzai.com) (Apple FoundationModels CLI), [Claude Code](https://docs.claude.com/claude-code) (OAuth 인증) |
| Vault | Obsidian (iCloud sync 권장) |

**RAG 의존성 (옵션):** `[rag]` extra 설치 시 `bge-m3` 임베딩 모델 ~2.3GB 다운로드.

## 빠른 시작

```bash
# 1. 설치
brew install Arthur-Ficial/tap/apfel        # Apple FoundationModels CLI
brew install uv                              # Python 패키지 매니저

git clone https://github.com/Jimmy-Jung/synapse-memory.git
cd synapse-memory/v2
uv venv --python 3.13
source .venv/bin/activate
uv pip install -e '.[rag]'                   # RAG 포함

# 2. 환경 진단 — 모든 항목 ✓ 이어야
synapse-memory doctor

# 3. raw 데이터 수집 (Claude Code 로그 + Obsidian vault)
synapse-memory collect claude-code
synapse-memory collect obsidian

# 4. Card 자동 생성 흐름
synapse-memory cluster scan                  # raw → 프로젝트 묶기
synapse-memory cluster classify              # project/company/domain/life 분류 (Claude haiku)
synapse-memory card generate                 # project/company kind만 자동 카드 생성 (Claude sonnet)

# 5. RAG 인덱싱
synapse-memory rag index

# 6. 사용 시작
synapse-memory ask "iOS 아키텍처 어떻게 설계했어?"
synapse-memory me draft-resume <company_id>
synapse-memory me decide "다음 회사 어디 지원할까"

# 7. 매일 한 줄 (5분 워크플로)
synapse-memory daily
```

## 아키텍처

```
[외부 데이터]
  Claude Code logs ──┐
  Obsidian vault ────┤
                     ▼
[L0]  ~/.synapse/private/raw/   (0700, 외부 LLM 노출 금지)
                     ▼
[Redaction]  Pass 1 (regex+validator) → Pass 2 (apfel, 로컬)
                     ▼  (redacted text만 외부 API로)
[Cluster 식별]  vault 폴더 + Claude Code cwd → ProjectCluster
                     ▼
[Card 자동 생성]  Claude (sonnet) → ProjectCard / CompanyCard
                     ▼
[L2 vault]  20_Reference/Projects/, Companies/
                     ▼
[RAG 인덱싱]  bge-m3 (로컬) → ChromaDB
                     ▼
[Endpoints]  ask, me draft-resume, me what-did-i-think, me decide,
             me update-profile, daily
```

## 명령 레퍼런스

### 환경 / 수집
- `doctor` — 환경 진단 + L0 setup
- `collect claude-code` — Claude Code 로그 incremental mirror
- `collect obsidian` — Obsidian vault mirror (mtime+size+hash 3-tier 변경 감지)

### Redaction
- `redact backfill claude-code` — L0 raw → redacted Pass 1+2
- `redactlist add/remove/show` — NDA 회사·프로젝트 강제 마스킹
- `eval golden` — 골든셋 평가 (P/R/F1)

### Card 파이프라인
- `cluster scan` — raw에서 프로젝트 클러스터 식별
- `cluster classify` — cluster를 project/company/domain/life/skip로 분류
- `card list/show/new/generate` — Card 관리

### RAG / 검색
- `rag index` — Card → 벡터 DB
- `rag search "<query>"` — dense 검색

### Endpoint (사용자 가치)
- `ask "<자연어>"` — RAG retrieve + Claude 합성
- `me draft-resume <company>` — 회사 맞춤 이력서 → vault Drafts
- `me what-did-i-think <topic>` — 시간순 회상
- `me decide <situation>` — Profile/DecisionPatterns 기반 의사결정
- `me update-profile` — ProfileFact / DecisionPattern 후보 → MemoryInbox PR

### 일일 통합
- `daily` — 모든 단계 incremental 실행 (5분 워크플로)
- `daily --dry-run` — 실행할 단계만 확인
- `daily --only collect_*,index` — 특정 단계만

## 보안 / 프라이버시 모델

1. **L0 격리**: `~/.synapse/private/` (0700). 모든 raw 데이터는 여기 격리.
2. **외부 LLM에 전달되는 입력은 항상 redacted**: Pass 1 (regex/validator) + Pass 2 (apfel 로컬 모델) 통과 후만.
3. **apfel = 로컬 모델**: raw 데이터를 외부 노출 없이 분류/태깅. Apple Silicon 전용.
4. **Claude Code CLI subprocess**: API key 별도 발급 불필요, 사용자 OAuth 그대로. `--system-prompt` 항상 명시로 cache 폭증 회피.
5. **redact-list**: 사용자 정의 NDA 회사 / 프로젝트 키워드 강제 마스킹.

## 6주 MVP 진행

```
W1 ✓ 인프라 (apfel wrapper + L0 + Pass 1+2 + 골든셋, F1=0.92)
W2 ✓ Obsidian collector (Claude Code는 W1)
W3 ✓ Card schema + cluster 식별 + auto-classify/generate
W4 ✓ RAG (bge-m3 + ChromaDB) + ask endpoint
W5 ✓ me {draft-resume, what-did-i-think, decide, update-profile}
W6 ✓ daily 통합 파이프라인

459 tests passed, ~5500줄
```

## 개발

```bash
# 테스트
uv pip install -e '.[dev]'
pytest -v

# 단위 검증 (apfel/Claude/임베딩 미사용 환경에서도 통과)
pytest tests/ -p no:cacheprovider

# 골든셋 평가 (apfel 필요)
synapse-memory eval golden --show-failures 15
```

## 알려진 한계 / 백로그

- **org_name 한국 회사 검출** F1=0.50 (메가스터디 등). 사용자 `redactlist`로 보완.
- **BM25 미사용** — dense (bge-m3)만으로 충분히 정확. 한국어 고유명사 검색에서 부족하면 추후 추가.
- **raw 노트 인덱싱 미지원** — Card만 검색. vault 1330+ 노트 RAG 확장은 backlog.
- **`★ Insight` 박스** — Claude Code explanatory mode가 가끔 system prompt를 우회. 답변 품질엔 영향 없음.

## License

MIT

## 저자

JunyoungJung <joony300@gmail.com>
