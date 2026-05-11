# Getting Started

처음 설치 + 첫 실행 가이드 (15-20분).

## 1. 시스템 요구사항 확인

| 항목 | 요구 |
|---|---|
| 하드웨어 | Apple Silicon (M1 이상) |
| OS | macOS Tahoe 26.0+ |
| Python | 3.11+ |

Intel Mac 또는 macOS 25 이하는 지원하지 않습니다 — `apfel`(Apple FoundationModels)이 동작하지 않습니다.

## 2. 외부 도구 설치

### apfel — Apple FoundationModels CLI

로컬 LLM (redaction Pass 2, Card 분류 등에 사용).

```bash
brew install Arthur-Ficial/tap/apfel
apfel --version    # apfel v1.3.x 이상
```

### Claude Code CLI

원격 LLM (Card 자동 생성, ask, me endpoints에 사용). 별도 API key 발급 불필요 — Pro/Max 구독 OAuth 그대로 사용.

```bash
# 이미 설치되어 있으면 skip
claude --version
```

설치 안 되어 있으면 [docs.claude.com/claude-code](https://docs.claude.com/claude-code).

### uv — Python 패키지 매니저

표준 venv 대신 `uv` 사용 권장 (macOS Tahoe에서 system Python venv가 깨지는 케이스 회피).

```bash
brew install uv
```

## 3. 저장소 복제 + 패키지 설치

```bash
git clone https://github.com/Jimmy-Jung/synapse-memory.git
cd synapse-memory/v2

# 격리된 Python 3.13 환경
uv venv --python 3.13
source .venv/bin/activate

# 패키지 설치 (RAG 의존성 포함)
uv pip install -e '.[rag]'
```

**의존성 분량:**
- 기본: `PyYAML`
- `[rag]`: `chromadb` + `sentence-transformers` + `torch` + `rank-bm25` (~1.5GB)
- `[dev]`: pytest + ruff + mypy

`[rag]` 미설치 시 `rag index/search`, `ask`, `me draft-resume/decide/what-did-i-think`가 동작하지 않습니다.

## 4. 환경 진단

```bash
synapse-memory doctor
```

기대 출력:
```
✓ apfel 설치: /opt/homebrew/bin/apfel
  버전: apfel v1.3.3
✓ Apple Silicon (arm64)
✓ macOS 26.2 (Tahoe+)
✓ L0 루트: /Users/jimmy/.synapse/private (0700)
✓ Claude Code CLI: /Users/jimmy/.local/bin/claude [2.1.x] (model=sonnet)

✓ 준비 완료
```

모든 항목 ✓이어야 진행 가능.

## 5. 첫 데이터 수집

```bash
# Claude Code 활동 로그
synapse-memory collect claude-code

# Obsidian vault (iCloud 동기 경로 기본)
synapse-memory collect obsidian
```

다른 vault 경로면:
```bash
export SYNAPSE_OBSIDIAN_VAULT="/path/to/your/vault"
synapse-memory collect obsidian
```

결과는 `~/.synapse/private/raw/` 아래에 mirror됩니다 (외부 노출 금지, 권한 0700).

## 6. Card 자동 생성 (선택 — 비용 발생)

vault에서 프로젝트 클러스터를 자동 식별하고 카드를 생성합니다.

```bash
# 1. raw → 프로젝트 클러스터
synapse-memory cluster scan

# 2. cluster를 project/company/domain/life/skip 분류 (~$0.04, haiku)
synapse-memory cluster classify --resume

# 3. project/company kind만 Card 자동 생성 (~$1-3, sonnet)
synapse-memory card generate

# 4. 결과 vault 확인
ls "$VAULT_PATH/20_Reference/Projects/"
ls "$VAULT_PATH/20_Reference/Companies/"
```

생성된 Card는 `status: draft`로 저장됩니다 — Obsidian에서 직접 검토·수정 후 `status: active`로 promote.

## 7. RAG 인덱싱

Card를 벡터 DB에 임베드합니다 (bge-m3 ~2.3GB 첫 다운로드, 5분).

```bash
synapse-memory rag index --rebuild
```

## 8. 첫 endpoint 사용

```bash
# 세컨드 브레인
synapse-memory ask "iOS 클린 아키텍처 어떻게 도입했지?"

# 의사결정 코파일럿
synapse-memory me decide "다음 회사 지원할 때 어떤 프로젝트 강조?"

# 회사 맞춤 이력서
synapse-memory me draft-resume danggeun
```

## 9. 일일 워크플로 등록 (선택)

매일 5분 한 줄로:

```bash
synapse-memory daily
```

`crontab -e`로 자동화:

```cron
# 매일 오전 8시
0 8 * * * cd ~/Documents/GitHub/synapse-memory/v2 && source .venv/bin/activate && synapse-memory daily --profile-facts-only
```

## 다음 단계

- [사용 시나리오](usage.md) — 이력서 작성 / 의사결정 / 주제 회상
- [아키텍처](architecture.md) — 설계 결정 + 데이터 흐름 + 보안
- [명령 레퍼런스](commands.md) — 모든 CLI 옵션
- [개발자 가이드](development.md) — 테스트 + 기여
