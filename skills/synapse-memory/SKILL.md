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
- "오늘자 정리 한 번 돌려" → `/synapse-daily`
- "환경 정상인지 봐줘" → `/synapse-doctor`

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
commands/                           # Claude Code slash 명령 (6개)
skills/synapse-memory/SKILL.md      # 양쪽이 공유하는 skill
```

Claude Code는 `commands/` + `skills/`를 모두 사용, Codex는 `skills/`만 사용합니다.

## CLI 백엔드 + 사용 정책

모든 slash 명령은 내부적으로 `synapse-memory` Python CLI를 `SYNAPSE_FROM_AGENT=1` env 와 함께 호출합니다:

| Slash | 내부 호출 | 종류 |
|---|---|---|
| `/synapse-ask` | `SYNAPSE_FROM_AGENT=1 synapse-memory ask "<질의>"` | 대화형 |
| `/synapse-recall` | `SYNAPSE_FROM_AGENT=1 synapse-memory me what-did-i-think "<주제>"` | 대화형 |
| `/synapse-decide` | `SYNAPSE_FROM_AGENT=1 synapse-memory me decide "<상황>"` | 대화형 |
| `/synapse-resume` | `SYNAPSE_FROM_AGENT=1 synapse-memory me draft-resume <회사>` | 대화형 |
| `/synapse-daily` | `synapse-memory daily` | 배치 |
| `/synapse-doctor` | `synapse-memory doctor` | 환경 진단 |

### 정책 (반드시 준수)

- **대화형 endpoint (`ask`, `me *`)** 는 사용자가 *터미널에서 직접* 호출하지 못하게 만류합니다. TTY 에서 부르면 3초 안내 메시지가 뜹니다.
- 사용자가 "터미널에서 `synapse-memory ask` 부르려는데 경고가 뜬다" 고 묻거든:
  1. `/synapse-ask` slash 명령 사용을 1순위로 권장
  2. 자동화 / 디버깅 목적이면 `SYNAPSE_FROM_AGENT=1` env 안내
- **배치 endpoint (`daily`, `doctor`, `collect`, `cluster`, `card`, `rag`, `redact`, `eval`)** 는 cron / LaunchAgent / CI 자동화 친화적. 자유롭게 CLI 사용 가능.
- CLI가 PATH에서 발견되지 않으면 `uv tool install --editable '.[rag]'` 또는 `source ~/Documents/GitHub/synapse-memory/.venv/bin/activate` 로 활성화하라고 안내하세요.

## 안전 규칙

- vault 파일을 *직접* 수정하지 마세요. 항상 CLI를 통해 처리 (CLI가 trash-first 보존 + diff 생성).
- 외부 LLM(Claude API)에 raw 데이터를 보내지 마세요. 항상 redaction pipeline 통과.
- `~/.synapse/private/` 내용을 chat에 그대로 노출하지 마세요.
- 이력서 / 결정 결과는 사용자 vault `30_Creative/Drafts/`에 저장된 파일 경로를 알려주고, 사용자가 수동 검토 후 공식화하도록 권장.

## 도움 / 진단

문제 발생 시 우선순위:
1. `/synapse-doctor` — 환경 진단
2. [docs/getting-started.md](https://github.com/Jimmy-Jung/synapse-memory/blob/main/docs/getting-started.md)
3. [docs/commands.md](https://github.com/Jimmy-Jung/synapse-memory/blob/main/docs/commands.md) — 전체 CLI 옵션
4. [GitHub Issues](https://github.com/Jimmy-Jung/synapse-memory/issues)
