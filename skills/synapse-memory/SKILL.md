---
name: synapse-memory
description: Use when the user asks to recall what they thought about a topic, draft a company-tailored resume, make a decision based on their past patterns, run daily ingest, or query their vault via RAG. Synapse Memory is a local-first AI assistant / second brain / clone backed by an Obsidian vault and Claude Code activity logs.
---

# Synapse Memory Skill

Synapse Memory는 macOS Apple Silicon 전용 local-first AI 메모리 파이프라인입니다.
Obsidian vault + Claude Code 활동 로그를 mirror·redact한 뒤 Project / Company Card를
자동 추출하고 RAG / 회상 / 의사결정 / 이력서 합성을 제공합니다.

## 언제 이 skill을 쓰는가

- 사용자가 "내가 X에 대해 뭐라 했었지?" 회상 → `/synapse-recall <주제>`
- "Y 회사 지원할건데 이력서 써줘" → `/synapse-resume <회사>`
- "Z 상황에서 어떻게 결정하지?" → `/synapse-decide <상황>`
- "vault에서 X 찾아줘" / 자연어 질의 → `/synapse-ask <질의>`
- "내 회고록/일기/메모를 학습시켜줘" → `persona ingest --file <path>` (M1b)
- "오늘자 정리 한 번 돌려" → `/synapse-daily`
- "환경 정상인지 봐줘" → `/synapse-doctor`
- "설치가 깨진 것 같아 / 고쳐줘" → `/synapse-fix`

## 외부 자료 학습 (`persona ingest`)

사용자의 **회고록 · 일기 · 외부 메모** 를 Persona 에 흡수해 말투 · 기술 선호 · 작업
방식을 더 풍부하게 만드는 경로입니다. 새 프로젝트 설계나 본인 스타일의 문서
생성을 하려면 이 자료가 두텁게 쌓여 있을수록 결과 품질이 높습니다.

```bash
synapse-memory persona ingest --file ~/Documents/diary-2025.md
synapse-memory persona ingest \
    --file ~/Documents/retro-q4.md \
    --file ~/Documents/proposal-draft.md
```

흐름:

1. raw 텍스트는 `~/.synapse/private/raw/persona/<sha-prefix>/` 에 0600 으로 mirror.
2. Pass 1+2 redaction 통과한 텍스트로 `extract_profile_facts` 호출.
3. 후보 ProfileFact 들이 `90_System/AI/MemoryInbox/Profile-YYYY-MM-DD.md` 에 PR 로 추가.
4. 사용자가 Obsidian 에서 PR 를 검토하고 accepted 항목만 `Profile.md` 로 복사.

지원 확장자: `.md`, `.markdown`, `.txt`. PDF · docx 등은 현재 unsupported.

## 새 프로젝트 설계 (`persona design-project`)

사용자가 "이런 아이디어로 새 프로젝트 시작" 이라고 할 때, **본인 기술 스택 ·
작업 방식 · 말투** 가 반영된 설계 초안을 `20_Projects/Drafts/` 에 생성합니다.
M1c 의 핵심 wedge 명령어.

```bash
synapse-memory persona design-project "iOS Todo 앱 새로 시작"
synapse-memory persona design-project "사내 RAG 검색 도구" --top-k 8
```

흐름:

1. vault `Profile.md` (`tech` / `work_style` / `voice` fact) + `DecisionPatterns.md` 로드.
2. ProjectCard RAG (`source_kind=card_project`) 로 유사 과거 프로젝트 검색.
3. LLM 이 system prompt 의 `[Profile: <category>]` 인용 규칙을 따라 설계 markdown 생성.
4. `20_Projects/Drafts/design_project - <idea> (YYYY-MM-DD).md` 저장.

권장 선행 작업:

- `persona ingest --file <외부자료>` 또는 `persona update-profile` 로 Profile 충분히 채우기.
- `Profile.md` 비어있으면 generic 답이 나오므로, `tech` 와 `work_style` 카테고리에 최소 2-3개 fact 가 있을 때 데모 가치가 가장 큼.

LLM 출력 규칙 (system prompt 에 내장):
- 모든 추천에 `[Profile: tech]` / `[Profile: work_style]` 같은 인용 강제.
- 사용자가 안 쓰는 프레임워크 (React/Flutter 등) 도입 금지.
- Profile 비어 있으면 generic 추천만 + 명시 경고.

## 핵심 보안 원칙 (반드시 준수)

| 원칙 | 의미 |
|---|---|
| **L0 격리** | 모든 raw 데이터는 `~/.synapse/private/` (0700)에 격리. vault에 raw 노출 금지. |
| **2-pass redaction** | regex (Pass 1, F1=1.00) + apfel 로컬 LLM (Pass 2, F1=0.83) — 외부 LLM 입력은 *항상* redacted. |
| **redact-list** | 사용자 정의 NDA 회사 / 프로젝트 키워드는 강제 마스킹. |
| **vault 진실원본** | `90_System/AI/Profile.md`, `DecisionPatterns.md`, `MemoryInbox/`는 사용자가 직접 검토. AI가 무단 수정 금지. |

## Plugin 호환성

같은 repo가 Claude Code와 Codex 두 플랫폼에서 동작합니다:

```
.claude-plugin/plugin.json          # Claude Code manifest
.claude-plugin/marketplace.json     # Claude Code marketplace
.codex-plugin/plugin.json           # Codex manifest
commands/                           # Claude Code slash 명령
skills/synapse-memory/SKILL.md      # 양쪽이 공유하는 skill
```

Claude Code는 `commands/` + `skills/`를 모두 사용, Codex는 `skills/`만 사용합니다.

## CLI 백엔드 + 사용 정책

모든 slash 명령은 내부적으로 `synapse-memory` Python CLI를 `SYNAPSE_FROM_AGENT=1` env 와 함께 호출합니다:

| Slash | 내부 호출 | 종류 |
|---|---|---|
| `/synapse-ask` | `SYNAPSE_FROM_AGENT=1 synapse-memory ask "<질의>"` | 대화형 |
| `/synapse-recall` | `SYNAPSE_FROM_AGENT=1 synapse-memory persona what-did-i-think "<주제>"` | 대화형 |
| `/synapse-decide` | `SYNAPSE_FROM_AGENT=1 synapse-memory persona decide "<상황>"` | 대화형 |
| `/synapse-resume` | `SYNAPSE_FROM_AGENT=1 synapse-memory persona draft-resume <회사>` | 대화형 |
| `/synapse-daily` | `synapse-memory daily` | 배치 |
| `/synapse-doctor` | `synapse-memory doctor` | 환경 진단 |
| `/synapse-fix` | `synapse-memory doctor --fix` | 환경 자동 복구 |

### 정책 (반드시 준수)

- **대화형 endpoint (`ask`, `me *`)** 는 사용자가 *터미널에서 직접* 호출하지 못하게 만류합니다. TTY 에서 부르면 3초 안내 메시지가 뜹니다.
- 사용자가 "터미널에서 `synapse-memory ask` 부르려는데 경고가 뜬다" 고 묻거든:
  1. `/synapse-ask` slash 명령 사용을 1순위로 권장
  2. 자동화 / 디버깅 목적이면 `SYNAPSE_FROM_AGENT=1` env 안내
- **배치 endpoint (`daily`, `doctor`, `collect`, `cluster`, `card`, `rag`, `redact`, `eval`)** 는 cron / LaunchAgent / CI 자동화 친화적. 자유롭게 CLI 사용 가능.
- **Installer mode (비개발자용)** 는 `installer/SynapseMemory-Installer.command`의 단일 setup consent가 vault setup, runtime bootstrap, plugin install, agent loading 같은 설치 단계만 포괄합니다.
- `reflect --apply`, archive/apply, MemoryInbox 승인 같은 운영 단계 메모리 쓰기는 Installer mode 동의 범위 밖이며, 계속 별도 승인이 필요합니다.
- CLI가 PATH에서 발견되지 않으면 `uv tool install --editable '.[rag]'` 또는 `source ~/Documents/GitHub/synapse-memory/.venv/bin/activate` 로 활성화하라고 안내하세요.

## 안전 규칙

- vault 파일을 *직접* 수정하지 마세요. 항상 CLI를 통해 처리 (CLI가 trash-first 보존 + diff 생성).
- 외부 LLM(Claude API)에 raw 데이터를 보내지 마세요. 항상 redaction pipeline 통과.
- `~/.synapse/private/` 내용을 chat에 그대로 노출하지 마세요.
- 이력서 / 결정 결과는 사용자 vault `30_Creative/Drafts/`에 저장된 파일 경로를 알려주고, 사용자가 수동 검토 후 공식화하도록 권장.

## 도움 / 진단

문제 발생 시 우선순위:
1. `/synapse-doctor` — 환경 진단
2. `/synapse-fix` — whitelisted 자동 복구
3. [docs/getting-started.md](https://github.com/Jimmy-Jung/synapse-memory/blob/main/docs/getting-started.md)
4. [docs/commands.md](https://github.com/Jimmy-Jung/synapse-memory/blob/main/docs/commands.md) — 전체 CLI 옵션
5. [GitHub Issues](https://github.com/Jimmy-Jung/synapse-memory/issues)
