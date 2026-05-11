# Synapse Memory

> 개인용 AI 비서 / 세컨드 브레인 / 클론 — vault 데이터 위에서 동작하는 RAG + 자동 메모리 시스템.

Obsidian vault와 Claude Code 활동 로그를 안전하게 mirror·redact한 뒤, 자동으로
Project / Company Card를 추출하고 회사별 맞춤 이력서를 합성하고 주제 회상 /
의사결정 코파일럿까지 동작하는 로컬-first 도구.

## 3가지 핵심 목표

| 목표 | endpoint | 동작 |
|---|---|---|
| **AI 비서** | `synapse-memory ask "<질의>"` | RAG retrieve + Claude 합성 + 출처 인용 |
| **세컨드 브레인** | `me what-did-i-think <주제>` | 시간순 회상, 입장 변화 분석 |
| **내 클론** | `me decide <상황>` | vault Profile.md + DecisionPatterns.md 기반 추천 |

데모 시나리오: `me draft-resume <회사>` — 회사 맞춤 이력서 자동 생성.

## 30초 미리보기

```bash
$ synapse-memory ask "iOS 클린 아키텍처 어떻게 도입했지?"

**Domain–Data–Presentation 3계층 분리 + Repository 패턴 + DIContainer 조합으로 도입했습니다.** [이력서-2026]

도입 기간 2024.01~05, Tuist 멀티 모듈화로 확장 (2024.03~07).
결과: 버그 수정 시간 71% 단축, 크래시율 2.1% → 0.8%.
```

```bash
$ synapse-memory me draft-resume danggeun
✓ 이력서 생성: ~/.../30_Creative/Drafts/Resume - 당근마켓 (2026-05).md
  매칭 ProjectCard (6): dansim-ios, 이력서-2026, mobile-ios-slc-tablet, ...
```

```bash
$ synapse-memory daily --profile-facts-only
[collect_claude_code]    0.0s  변경 없음
[collect_obsidian]       0.2s  scanned=1356 mirrored=3 ...
[classify]               0.8s  신규 cluster 없음
[generate]               18.7s  신규 Card 1개 생성
[index]                  26.5s  project=11 company=2
[update_profile]         47.6s  fact=15 → MemoryInbox PR

Daily 총 시간: 93.8s
```

## 시스템 요구사항

| 항목 | 요구 |
|---|---|
| 하드웨어 | Apple Silicon (M1 이상) |
| OS | macOS Tahoe 26.0+ |
| Python | 3.11+ |
| 외부 도구 | [apfel](https://apfel.franzai.com), [Claude Code](https://docs.claude.com/claude-code) |
| Vault | Obsidian (iCloud sync 권장) |

Intel Mac · macOS 25 이하는 지원하지 않습니다 (apfel 의존).

## 빠른 시작

```bash
brew install Arthur-Ficial/tap/apfel
brew install uv

git clone https://github.com/Jimmy-Jung/synapse-memory.git
cd synapse-memory
uv venv --python 3.13
source .venv/bin/activate
uv pip install -e '.[rag]'

synapse-memory doctor              # 환경 진단
synapse-memory collect claude-code # raw 수집
synapse-memory collect obsidian
synapse-memory cluster classify    # 자동 분류
synapse-memory card generate       # Card 자동 생성
synapse-memory rag index           # 벡터 인덱싱
synapse-memory ask "<질의>"         # 사용 시작
```

상세: **[docs/getting-started.md](docs/getting-started.md)**.

## 보안 모델

- **L0 격리**: `~/.synapse/private/` (0700). 모든 raw 데이터는 여기 격리.
- **2-pass redaction**: regex (Pass 1, F1=1.00) + apfel 로컬 LLM (Pass 2, F1=0.83).
- **외부 LLM 입력 = 항상 redacted**: Claude Code 호출 시 raw 노출 없음.
- **redact-list**: 사용자 정의 NDA 회사 / 프로젝트 키워드 강제 마스킹.
- **Claude Code CLI subprocess**: API key 별도 발급 불필요, OAuth 그대로.

## 문서

- [Getting Started](docs/getting-started.md) — 설치 + 첫 실행 (15-20분)
- [사용 시나리오](docs/usage.md) — 일일 워크플로 / 이력서 / 의사결정 / 회상
- [아키텍처](docs/architecture.md) — 5가지 설계 결정 + 4-tier 메모리 + 보안 모델
- [CLI 레퍼런스](docs/commands.md) — 모든 명령 옵션 + 시나리오 예시
- [개발자 가이드](docs/development.md) — 코드 구조 + 테스트 + 기여
- [Backlog](docs/backlog.md) — 알려진 한계 + W6 패치 후보 + 확장 로드맵

## 진행 상황

```
W1 ✓ 인프라 (apfel + L0 + Pass 1+2, F1=0.92)
W2 ✓ Obsidian collector
W3 ✓ Card schema + cluster + auto-classify/generate
W4 ✓ RAG (bge-m3 + ChromaDB) + ask endpoint
W5 ✓ me {draft-resume, what-did-i-think, decide, update-profile}
W6 ✓ daily 통합 + 문서화 + GitHub publish

459 tests passed · ~5500줄 · v0.1.0
```

## 라이선스

MIT — [LICENSE](LICENSE).

## 저자

JunyoungJung <joony300@gmail.com>
