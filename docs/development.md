# 개발자 가이드

## 코드 구조

```
src/synapse_memory/
├── __init__.py
├── cli.py                  # 통합 CLI 진입점
├── daily.py                # 일일 파이프라인
│
├── llm/                    # LLM wrapper
│   ├── apfel.py            # Apple FoundationModels CLI (로컬)
│   ├── claude.py           # Claude Code CLI subprocess (원격)
│   └── credentials.py      # API key 관리 (현재 미사용)
│
├── storage/
│   └── l0.py               # ~/.synapse/private 0700 격리
│
├── collectors/             # 외부 데이터 → L0 mirror
│   ├── claude_code/mirror.py
│   └── obsidian/mirror.py
│
├── redaction/              # PII 마스킹
│   ├── patterns.py         # Pass 1 정규식 + validator
│   ├── pass1.py            # 결정적 redaction
│   ├── pass2_prompts.py    # apfel 시스템 프롬프트
│   ├── pass2.py            # LLM-based + 휴리스틱
│   └── redactlist.py       # NDA 강제 마스킹
│
├── eval/
│   └── golden.py           # 골든셋 P/R/F1 측정
│
├── clusters/
│   └── identify.py         # raw → ProjectCluster
│
├── cards/                  # Card 모델 + 자동 추출
│   ├── project.py          # ProjectCard schema/I/O
│   ├── company.py          # CompanyCard schema/I/O
│   ├── auto_classify.py    # cluster → kind (Claude haiku)
│   └── auto_generate.py    # cluster → Card draft (Claude sonnet)
│
├── rag/                    # 벡터 검색
│   ├── embeddings.py       # bge-m3
│   ├── vector_store.py     # ChromaDB wrapper
│   └── indexer.py          # Card → 벡터 DB
│
├── endpoints/              # 사용자 가치 layer
│   ├── ask.py              # 자연어 질의 → RAG → Claude
│   └── me.py               # draft-resume + what-did-i-think + decide
│
└── profile/                # 클론 인프라
    ├── schema.py           # ProfileFact / DecisionPattern
    └── extract.py          # raw → MemoryInbox PR
```

테스트는 `tests/test_<module>_*.py` 패턴.

## 테스트

### 단위 테스트 (외부 의존성 없이)

```bash
pytest -v
```

mock 위주라 apfel / Claude Code CLI / bge-m3 / chromadb 미설치 환경에서도 통과.

### 통합 테스트 (실제 LLM 호출)

```bash
# RAG 의존성 필요
uv pip install -e '.[rag]'

# 실제 검증 (apfel + Claude Code 호출)
synapse-memory eval golden --show-failures 10
```

### 단일 모듈

```bash
pytest tests/test_redaction_pass1.py -v
pytest tests/test_cards_auto_generate.py -v
```

### 커버리지

```bash
pytest --cov=synapse_memory --cov-report=term-missing
```

## Lint / Format

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/synapse_memory
```

## 새 endpoint 추가

예: `me draft-reply` (메시지 답장 초안).

1. `endpoints/me.py`에 함수 + dataclass 추가
2. `cli.py`에 `cmd_me_draft_reply` + argparse subcommand
3. `tests/test_endpoints_me_extra.py`에 mock 테스트
4. (필요 시) `docs/commands.md` + `docs/usage.md` 갱신

## 새 수집기 추가

예: Gmail (`collectors/gmail/`).

1. `collectors/gmail/__init__.py`, `mirror.py`
2. `mirror()`가 `~/.synapse/private/raw/gmail/`로 저장 (incremental)
3. CLI `collect gmail` 추가
4. `daily.py` STEPS에 `collect_gmail` 추가
5. 테스트

## 골든셋 갱신

`tests/golden/pii_synthetic.json`에 새 케이스 추가:

```json
{
  "id": "phone-006",
  "text": "+82-2-1234-5678",
  "expected": [{"category": "phone_kr", "value": "+82-2-1234-5678"}]
}
```

이후:
```bash
synapse-memory eval golden
```

F1 변화 확인.

## 디버깅

### apfel 호출 디버깅

```bash
# 직접 호출
echo "한국어 테스트" | apfel --print
apfel --help | head -50
```

`synapse_memory.llm.apfel.complete()` wrapper는 stdout만 반환. 디버깅 시 stderr 직접 보기:

```python
import subprocess
r = subprocess.run(["apfel", ...], capture_output=True, text=True)
print(r.stderr)
```

### Claude Code CLI 디버깅

```bash
# 우리 wrapper와 같은 옵션
claude --print --output-format json --no-session-persistence \
  --permission-mode bypassPermissions --model sonnet \
  --system-prompt "JSON만" "한국 수도?" 2>&1 | jq .
```

`is_error: true` + `result: "Not logged in"` 보이면 OAuth 인증 필요. `--bare` 절대 사용 금지.

### 임베딩 모델 다운로드

```bash
python -c "
from synapse_memory.rag import get_embedder
m = get_embedder()
print(m)
"
```

첫 호출 시 ~2.3GB `BAAI/bge-m3` 다운로드. 이후 캐시.

### Chroma persistent DB 위치

```bash
ls ~/.synapse/private/rag/chroma/
```

`--rebuild`로 collection 비우고 재인덱싱 가능.

## 새 모델 사용

```bash
# claude --model 옵션에 직접 alias 또는 full name
synapse-memory ask "..." --model haiku
synapse-memory ask "..." --model opus
synapse-memory ask "..." --model claude-sonnet-4-6
```

`synapse_memory.llm.claude.DEFAULT_MODEL` 갱신해서 default 변경 가능.

## 비용 모니터링

각 Claude 호출 응답에 `total_cost_usd` 필드. `synapse_memory.llm.claude._run_claude`에서 envelope dict 반환되므로 caller가 capture 가능:

```python
envelope = claude_api._run_claude(cmd, prompt="...", timeout=60)
print(envelope.get("total_cost_usd"))
```

(현재 wrapper API는 `envelope.result`만 노출. 비용 추적 endpoint는 W6 backlog.)

## 기여

- Bug report / Feature request: GitHub Issues
- Pull request 환영. 단:
  - 테스트 통과 (`pytest -v`)
  - 의존성 추가 시 사유 명시
  - 핵심 설계 결정 5가지 (Tier-3, 일일 5분, apfel, Apple Silicon+Tahoe, redacted-only)에 부합

## 라이선스

MIT — 자유롭게 사용/수정/배포 가능.
