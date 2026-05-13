# Synapse Memory

> 개인용 AI 비서 / 세컨드 브레인 / 클론 —
> vault 데이터 위에서 동작하는 RAG + 자동 메모리 시스템.

Obsidian vault와 Claude Code 활동 로그를 안전하게 mirror·redact한 뒤, 자동으로
Project / Company Card를 추출하고 회사별 맞춤 이력서를 합성하고 주제 회상 /
의사결정 코파일럿까지 동작하는 로컬-first 도구.

## 3가지 핵심 목표

| 목표 | CLI | Slash (Claude Code / Codex) |
|---|---|---|
| **AI 비서** | `synapse-memory ask "<질의>"` | `/synapse-ask <질의>` |
| **세컨드 브레인** | `me what-did-i-think <주제>` | `/synapse-recall <주제>` |
| **내 클론** | `me decide <상황>` | `/synapse-decide <상황>` |

데모 시나리오:
`me draft-resume <회사>` 또는 `/synapse-resume <회사>`로
회사 맞춤 이력서를 자동 생성합니다.

## 사용 정책 — 누가 어디서 부르는가

| 경로 | 누가 쓰는가 | 어떤 endpoint |
|---|---|---|
| **`/synapse-ask`, `/synapse-recall`, `/synapse-decide`, `/synapse-resume`** | **사람** — Claude Code / Codex 대화 안에서 | 대화형 (LLM 컨텍스트 필요) |
| **터미널 `synapse-memory ask "..."` 직접 호출** | **AI subprocess** + 디버깅 / 긴급 우회 | 대화형 (직접 호출은 만류) |
| **`synapse-memory daily / doctor / collect / cluster / card / rag / redact / eval`** | **사람 또는 자동화** (cron / LaunchAgent / CI) | 배치 / 유지보수 |

**왜 분리하나?**
AI 비서 · 세컨드 브레인 · 클론의 가치는 *LLM 대화 컨텍스트 안*에서 발생합니다.
터미널에서 직접 `ask`를 부르면 답은 받지만 후속 질문에 컨텍스트가 끊깁니다.

그래서 대화형 endpoint(`ask`, `me *`)는 TTY 직접 호출 시 3초 안내 후 진행합니다.
`SYNAPSE_FROM_AGENT=1` env가 있으면 즉시 통과하며,
slash command markdown이 이 값을 자동으로 설정합니다.
배치 endpoint는 항상 자유롭게 실행할 수 있습니다.

## 30초 미리보기

```bash
$ synapse-memory ask "iOS 클린 아키텍처 어떻게 도입했지?"

**Domain–Data–Presentation 3계층 분리 + Repository 패턴 +
DIContainer 조합으로 도입했습니다.** [이력서-2026]

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

### 비개발자 모드 — 더블클릭 설치

[v0.6.0 릴리스 zip][release-zip]을 받은 뒤
`installer/SynapseMemory-Installer.command`를 더블클릭합니다.

설치 프로그램은 GUI 동의 후 Homebrew, Obsidian, Claude Code, apfel,
Synapse runtime, Obsidian vault 후보를 순서대로 확인합니다.
저장소 위치는 GUI에서 선택하며, iCloud Obsidian 폴더가 있으면
`iCloud/SynapseVault`를 추천 위치로 보여줍니다.

현재 MVP installer는 안전을 위해 기본값이 dry-run/preview입니다.
실제 적용 모드는 constitution의 Installation Consent Scoping 정책이
반영된 뒤 활성화합니다.
로그는 `~/Library/Logs/SynapseMemory/` 아래에 남습니다.

문제가 생기면 자동 복구 가능한 항목만 고칩니다.

```bash
synapse-memory doctor --fix
```

### 개발자 모드 — 수동 설치

#### 1. 의존성

```bash
brew install apfel
brew install uv
```

#### 2. 설치 — 선택 (둘 중 하나)

```bash
git clone <repository-url>
cd synapse-memory
```

**(A) 글로벌 CLI 설치 (권장 — 어디서든 `synapse-memory` 호출 가능)**

```bash
uv tool install --editable '.[rag]'
```

**(B) Venv 격리 설치 (개발 / 실험용)**

```bash
uv venv --python 3.13
source .venv/bin/activate
uv pip install -e '.[rag]'
```

#### 3. 첫 실행

```bash
synapse-memory doctor              # 환경 진단
synapse-memory doctor --fix        # 자동 복구 가능한 항목만 복구
synapse-memory daily               # 한 번에 collect → cluster → card → index → profile
synapse-memory ask "<질의>"         # 사용 시작
```

#### 4. Claude Code / Codex slash 명령 활성화

설치 후 Claude Code / Codex가 이 repo를 plugin으로 로드하면
슬래시 명령이 자동 등록됩니다.

| Slash | 동작 |
|---|---|
| `/synapse-ask <질의>` | 자연어 질의 → RAG → Claude 답변 |
| `/synapse-recall <주제>` | 시간순 회상 |
| `/synapse-decide <상황>` | 의사결정 코파일럿 |
| `/synapse-resume <회사>` | 회사 맞춤 이력서 |
| `/synapse-daily` | 일일 통합 파이프라인 |
| `/synapse-doctor` | 환경 진단 |
| `/synapse-fix` | 환경 자동 복구 |

> slash 명령은 내부적으로 위 CLI를 호출하므로,
> **(A) 글로벌 설치 모드**를 권장합니다.

상세: **[docs/getting-started.md](docs/getting-started.md)** · **[docs/commands.md](docs/commands.md)**.

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
W6 ✓ daily 통합 + 문서화 + GitHub publish (v0.3.0)
W7 ✓ Claude Code / Codex plugin layer 부활 (v0.4.0+) — slash 명령 surface
W8 ✓ me-recipes framework + hybrid retrieval (v0.5.0) — recipe 기반 생성 + dense/BM25 선택
W9 ✓ 비개발자 온보딩 (v0.6.0) — 더블클릭 installer preview + iCloud vault 추천 + doctor --fix

686 tests passed · v0.6.0
```

## 라이선스

MIT — [LICENSE](LICENSE).

## 저자

Synapse Memory Maintainers

[release-zip]: https://github.com/Jimmy-Jung/synapse-memory/archive/refs/tags/v0.6.0.zip
