# Getting Started

설치부터 첫 질문까지 15-20분 정도 걸립니다. 이 문서는 "일단 동작하게 만들기"에 집중합니다.

## 어떤 상태에서 어디부터 보면 되나

| 상태 | 가는 곳 |
|---|---|
| "터미널 못 켜는 비개발자" | [§0 비개발자라면](#0-비개발자라면) → [installer-walkthrough.md](for-everyone/installer-walkthrough.md) |
| "Mac이 M1이고 macOS 26인지 확인하고 싶다" | [§1 준비물 확인](#1-준비물-확인) |
| "apfel·uv·Claude Code가 설치되어 있는지 모름" | [§2 도구 설치](#2-도구-설치) |
| "synapse-memory 명령을 어디서나 부르고 싶다" | [§3 모드 A — 글로벌 설치](#모드-a--글로벌-cli-설치-권장) |
| "소스 자주 고치니까 격리 환경이 좋다" | [§3 모드 B — Venv 격리](#모드-b--venv-격리-설치-개발--실험용) |
| "Claude Code / Codex 안에서 슬래시 명령 활성화" | [§3a plugin 활성화](#3a-claude-code--codex-plugin-활성화) |
| "지금 환경이 준비됐는지 확인하고 싶다" | [§4 환경 진단](#4-환경-진단) |
| "Obsidian vault 경로 자동 인식 실패" | [§5 vault 경로 지정](#5-obsidian-vault-경로-지정) |
| "첫 데이터를 모으고 카드를 만들고 싶다" | [§6~§9 첫 실행](#6-첫-데이터-수집) |
| "매일 자동 실행하고 싶다" | [§10 매일 실행하기](#10-매일-실행하기) |
| "뭔가 안 된다" | [문제가 생기면](#문제가-생기면) |

## 0. 비개발자라면

릴리스 zip을 받은 뒤 `installer/SynapseMemory-Installer.command`를 더블클릭합니다. 설치 프로그램은 GUI 동의 후 필요한 도구와 Obsidian vault 후보를 확인하고, 저장소 위치 선택창을 보여준 뒤 `~/Library/Logs/SynapseMemory/` 아래에 로그와 상태 manifest를 남깁니다. iCloud Obsidian 폴더가 있으면 `iCloud/SynapseVault`가 추천 위치로 표시됩니다.

현재 installer MVP는 기본값이 dry-run/preview입니다. 실제 적용 모드는 설치 단계 단일 동의 정책이 constitution에 반영된 뒤 활성화됩니다.

설치 후 문제가 생기면 다음 명령을 실행합니다.

```bash
synapse-memory doctor --fix
```

개발자이거나 직접 CLI 환경을 구성하려면 아래 수동 설치 절차를 사용합니다.

## 1. 준비물 확인

| 항목 | 필요 조건 |
| --- | --- |
| Mac | Apple Silicon, M1 이상 |
| OS | macOS Tahoe 26.0 이상 |
| Python | 3.11 이상 |
| Obsidian | vault 하나 이상 |
| Claude Code | 로그인된 CLI |

Intel Mac이나 macOS 25 이하는 지원하지 않습니다. 로컬 redaction에 쓰는 `apfel`이 Apple FoundationModels를 사용하기 때문입니다.

## 2. 도구 설치

`apfel`은 로컬 LLM 작업에 필요합니다.

```bash
brew install apfel
apfel --version
```

`uv`는 Python 환경과 패키지 설치에 사용합니다.

```bash
brew install uv
```

Claude Code CLI가 이미 설치되어 있고 로그인되어 있는지 확인합니다.

```bash
claude --version
```

설치가 필요하면 Claude Code 공식 문서의 설치 안내를 따릅니다.

## 3. Synapse Memory 설치 — 두 모드 중 선택

```bash
git clone <repository-url>
cd synapse-memory
```

### 모드 A — 글로벌 CLI 설치 (권장)

매일 사용자는 이 모드를 선택합니다. `synapse-memory` 바이너리가 사용자 PATH에 등록되어 어디서든 호출 가능 — Claude Code / Codex slash 명령도 이 모드를 가정합니다.

```bash
uv tool install --editable '.[rag]'
synapse-memory --version
```

이후 venv activate가 필요하지 않습니다.

### 모드 B — Venv 격리 설치 (개발 / 실험용)

소스를 자주 고치거나 격리된 환경이 필요할 때만 선택합니다.

```bash
uv venv --python 3.13
source .venv/bin/activate
uv pip install -e '.[rag]'
```

> 이 모드에서는 매번 `source .venv/bin/activate`가 필요하며, slash 명령은 이 venv가 활성화된 셸에서 Claude Code/Codex를 실행해야 동작합니다.

`[rag]` 옵션은 검색과 질문 기능에 필요합니다. 첫 설치 때 `chromadb`, `sentence-transformers`, `torch`, `rank-bm25`가 함께 설치됩니다.

개발까지 할 예정이면 다음도 설치합니다.

```bash
uv pip install -e '.[dev,rag]'
```

## 3a. Claude Code / Codex plugin 활성화

이 repo는 Claude Code / Codex 양쪽 plugin manifest를 포함합니다 (`.claude-plugin/`, `.codex-plugin/`). plugin이 로드되면 Synapse slash 명령이 자동 등록됩니다.

```
/synapse-ask <질의>        /synapse-recall <주제>     /synapse-decide <상황>
/synapse-resume <회사>     /synapse-daily             /synapse-doctor
/synapse-fix
```

Claude Code 의 plugin 등록 방법은 Claude Code 공식 문서의 plugin / marketplace 가이드를 따릅니다. Codex 의 경우 `.codex-plugin/plugin.json` 을 marketplace 로 가리키면 됩니다. slash 호출은 모두 위 CLI를 subprocess 로 실행하므로 모드 A 글로벌 설치가 가장 안정적입니다.

## 4. 환경 진단

```bash
synapse-memory doctor
```

정상이라면 대략 이런 항목이 표시됩니다.

```text
✓ apfel 설치: /opt/homebrew/bin/apfel
✓ Apple Silicon (arm64)
✓ macOS 26.x (Tahoe+)
✓ L0 루트: /Users/<you>/.synapse/private (0700)
✓ Claude Code CLI: ... (model=sonnet)
✓ 준비 완료
```

여기서 실패가 나오면 먼저 그 항목을 해결합니다. 특히 `L0 루트`는 원본 로그가 저장되는 비공개 디렉터리라 권한이 `0700`이어야 합니다.

자동 복구 가능한 항목은 다음 명령으로 처리할 수 있습니다.

```bash
synapse-memory doctor --fix
```

## 5. Obsidian vault 경로 지정

기본 경로를 자동으로 찾지 못하면 환경변수로 vault를 지정합니다.

```bash
export SYNAPSE_OBSIDIAN_VAULT="/path/to/your/vault"
```

이 값을 계속 쓰려면 사용하는 shell 설정 파일에 추가합니다.

## 6. 첫 데이터 수집

Claude Code 로그와 Obsidian vault를 `~/.synapse/private/raw/` 아래로 mirror합니다.

```bash
synapse-memory collect claude-code
synapse-memory collect obsidian
```

이 단계는 원본을 복사할 뿐입니다. 원본 raw 데이터는 외부 LLM에 보내지 않습니다.

## 7. Card 만들기

Card는 프로젝트와 회사를 요약한 Obsidian 문서입니다. 질문, 회상, 이력서 생성의 주요 재료가 됩니다.

```bash
synapse-memory cluster scan
synapse-memory cluster classify --resume
synapse-memory card generate
```

생성된 Card는 vault의 아래 위치에 저장됩니다.

```text
20_Reference/Projects/
20_Reference/Companies/
```

처음 생성된 Card는 보통 `status: draft`입니다. Obsidian에서 내용을 검토하고 맞으면 `status: active`로 바꿉니다.

## 8. 검색 인덱스 만들기

Card를 로컬 벡터 DB에 넣습니다. 첫 실행 때 임베딩 모델을 다운로드하므로 몇 분 걸릴 수 있습니다.

```bash
synapse-memory rag index --rebuild
```

## 9. 첫 질문하기

```bash
synapse-memory ask "iOS 클린 아키텍처 어떻게 도입했지?"
```

이제 다음 기능도 사용할 수 있습니다.

```bash
synapse-memory persona what-did-i-think "TCA 아키텍처"
synapse-memory persona decide "다음 회사 지원할 때 어떤 프로젝트를 강조할까?"
synapse-memory persona draft-resume examplecorp

# 외부 자료 (회고록·일기) 흡수해서 Persona 보강
synapse-memory persona ingest --file ~/Documents/diary-2025.md

# 새 프로젝트를 내 스타일로 설계
synapse-memory persona design-project "iOS Todo 앱 새로 시작"
```

> 두 번째 명령 (`persona ingest`) 으로 외부 markdown / txt 를 흡수하면 `tech` · `work_style` · `voice` 카테고리에 후보가 쌓입니다. 세 번째 (`persona design-project`) 의 결과 품질은 Profile 의 두께에 직접 비례합니다.

## 10. 매일 실행하기

수동으로는 하루 한 번 이 명령을 실행하면 됩니다.

```bash
synapse-memory daily --profile-facts-only
```

cron으로 돌릴 때는 저장소 루트에서 venv를 활성화한 뒤 실행합니다.

```cron
0 8 * * * cd ~/Documents/GitHub/synapse-memory && . .venv/bin/activate && synapse-memory daily --profile-facts-only
```

## 문제가 생기면

| 증상 | 먼저 확인할 것 |
| --- | --- |
| `apfel 미설치` | `brew install apfel` |
| `Claude Code CLI 미설치` | `claude --version`, Claude Code 로그인 상태 |
| vault를 못 찾음 | `SYNAPSE_OBSIDIAN_VAULT` 값 |
| 검색 결과 없음 | `synapse-memory rag index --rebuild` 실행 여부 |
| Card가 없음 | `cluster classify`, `card generate` 실행 여부 |
| LaunchAgent 또는 runtime shim 문제 | `synapse-memory doctor --fix` |

다음은 [사용 시나리오](usage.md)에서 실제 workflow별 예시를 보면 됩니다.
