# 개발자 가이드

이 문서는 Synapse Memory를 수정하거나 기능을 추가할 때 필요한 최소 맥락을 정리합니다.

## 개발 환경

```bash
cd synapse-memory
uv venv --python 3.13
source .venv/bin/activate
uv pip install -e '.[dev,rag]'
```

기본 확인:

```bash
synapse-memory doctor
pytest -v
ruff check src/ tests/
mypy src/synapse_memory
```

## 코드 구조

```text
src/synapse_memory/
├── __init__.py
├── cli.py                  # argparse 기반 CLI
├── daily.py                # 일일 파이프라인 orchestration
├── llm/                    # apfel, Claude Code CLI wrapper
├── storage/                # L0 private directory 관리
├── collectors/             # 외부 데이터 mirror
├── redaction/              # PII/NDA 마스킹
├── eval/                   # golden set 평가
├── clusters/               # raw를 프로젝트/회사 후보로 묶기
├── cards/                  # ProjectCard, CompanyCard, 자동 생성
├── rag/                    # embedding, vector store, indexer
├── endpoints/              # ask, me commands
└── profile/                # ProfileFact, DecisionPattern 추출
```

테스트는 `tests/test_<module>.py` 또는 `tests/test_<feature>.py` 형태입니다.

## 중요한 설계 규칙

- L0 raw는 외부 LLM에 직접 보내지 않습니다.
- 자동 생성 결과는 초안입니다. 사용자가 vault에서 승인한 문서가 truth source입니다.
- 기존 Card는 기본적으로 덮어쓰지 않습니다. 덮어쓰기는 명시적인 `--force`에서만 합니다.
- collector는 incremental하고 재실행 가능해야 합니다.
- 새 endpoint는 출처를 인용하고, 자료에 없는 내용은 없다고 말해야 합니다.

## 테스트

전체 테스트:

```bash
pytest -v
```

단일 영역 테스트:

```bash
pytest tests/test_redaction_pass1.py -v
pytest tests/test_cards_auto_generate.py -v
pytest tests/test_endpoints_me.py -v
```

커버리지:

```bash
pytest --cov=synapse_memory --cov-report=term-missing
```

대부분의 테스트는 mock 기반이라 apfel, Claude Code CLI, ChromaDB가 없어도 통과하도록 유지합니다. 실제 LLM이나 임베딩을 부르는 검증은 별도로 실행합니다.

## Observability Snapshots

Constitution [Principle V](../.specify/memory/constitution.md#principle-v-reproducible-daily-pipeline--observability) 에 따라 stage별로 사람이 읽을 수 있는 관측 라인을 유지합니다.
`me generate <recipe>` 는 stdout 에 생성 결과를 쓰고, stderr 에 한 줄 snapshot 을 남깁니다.

```text
[me.generate.weekly_report] source=builtin rag_mode=hybrid locale=profile:한국어 domain=tags:software profile_used=True matched=4 duration=2841ms
```

| 토큰 | 의미 |
| --- | --- |
| `source` | 실행된 recipe 출처. `builtin`, `user`, 또는 보조 scan 실패 시 `?` |
| `rag_mode` | 이번 호출의 effective retrieval mode. recipe frontmatter 또는 `--rag-mode` override 적용 후 값 |
| `locale` | `<source>:<locale>` 형식. CLI, company card, profile, default 중 어디서 결정됐는지 표시 |
| `domain` | `<source>:<domain>` 형식. CLI, profile, matched record tags, default 중 어디서 결정됐는지 표시 |
| `profile_used` | Profile/DecisionPatterns 계열 텍스트가 prompt 에 포함됐는지 여부 |
| `matched` | downstream prompt와 last_answer citation 후보로 전달된 source id 수 |
| `duration` | CLI orchestration 시작부터 결과 출력 직전까지의 밀리초 |

`rag_mode=hybrid` 에서 BM25 sidecar 또는 vector store 가 없으면 dense fallback 없이 실패하고,
stderr 에 `synapse-memory rag index --include-raw` 재색인 안내를 출력해야 합니다.

## Lint와 format

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/synapse_memory
```

`pyproject.toml`의 ruff line length는 100입니다.

## 새 endpoint 추가

예: `synapse-memory me draft-reply`

1. `src/synapse_memory/endpoints/`에 핵심 로직을 추가합니다.
2. 필요하면 dataclass나 schema를 같은 feature 경계 안에 둡니다.
3. `src/synapse_memory/cli.py`에 argparse subcommand를 추가합니다.
4. `tests/`에 mock 기반 단위 테스트를 추가합니다.
5. [commands.md](commands.md)와 [usage.md](usage.md)를 갱신합니다.

endpoint 구현에서 확인할 것:

- 입력 validation
- 모델 호출 실패 처리
- 빈 검색 결과 처리
- 출처 인용
- raw 비노출

## 새 collector 추가

예: Gmail collector

1. `src/synapse_memory/collectors/gmail/` 모듈을 만듭니다.
2. `mirror.py`는 `~/.synapse/private/raw/gmail/` 아래에 저장합니다.
3. 변경분만 처리하도록 cursor, timestamp, hash 중 적절한 방식을 둡니다.
4. `cli.py`에 `collect gmail`을 추가합니다.
5. `daily.py`의 `STEPS`에 필요 단계를 추가합니다.
6. 테스트에서는 외부 API를 mock 처리합니다.

collector는 같은 입력을 여러 번 실행해도 결과가 안정적이어야 합니다.

## Redaction 패턴 추가

Pass 1 패턴을 추가할 때는 보통 이 순서로 작업합니다.

1. `tests/golden/pii_synthetic.json`에 실패 케이스를 먼저 추가합니다.
2. `src/synapse_memory/redaction/patterns.py`에 regex와 validator를 추가합니다.
3. `tests/test_redaction_pass1.py`를 보강합니다.
4. `synapse-memory eval golden`으로 precision, recall, F1 변화를 확인합니다.

골든셋 예시:

```json
{
  "id": "phone-006",
  "text": "+82-2-1234-5678",
  "expected": [{"category": "phone_kr", "value": "+82-2-1234-5678"}]
}
```

## Card schema 변경

ProjectCard나 CompanyCard를 바꿀 때는 아래를 함께 확인합니다.

- schema dataclass
- serialize / load 함수
- auto_generate prompt와 parser
- 기존 vault Card와의 호환성
- `card show`, `card list`
- RAG index metadata
- 문서 예시

사용자가 직접 편집한 Card가 깨지지 않는 방향을 우선합니다.

## 디버깅

### apfel

```bash
echo "한국어 테스트" | apfel --print
apfel --help | head -50
```

Python wrapper를 우회해 stderr를 보고 싶을 때:

```python
import subprocess

r = subprocess.run(["apfel", "--print"], input="테스트", capture_output=True, text=True)
print(r.stdout)
print(r.stderr)
```

### Claude Code CLI

wrapper와 비슷한 방식으로 직접 호출합니다.

```bash
claude --print --output-format json --no-session-persistence \
  --permission-mode bypassPermissions --model sonnet \
  --system-prompt "JSON만 출력" "한국 수도?" 2>&1 | jq .
```

`Not logged in`이 나오면 Claude Code 인증 상태를 확인합니다.

### 임베딩과 ChromaDB

```bash
python -c "from synapse_memory.rag import get_embedder; print(get_embedder())"
ls ~/.synapse/private/rag/chroma/
```

첫 임베딩 호출은 모델 다운로드 때문에 오래 걸릴 수 있습니다.

## 비용 확인

Claude Code CLI 응답 envelope에는 비용 관련 필드가 포함될 수 있습니다. 현재 사용자용 비용 요약 endpoint는 없고, 비용 추적 기능은 backlog에 있습니다.

개발 중에는 아래 원칙을 지킵니다.

- 단위 테스트에서는 Claude 호출을 mock 처리합니다.
- `--limit` 옵션으로 작은 입력부터 검증합니다.
- Card 자동 생성은 기존 파일을 기본 skip하게 둡니다.

## 문서 갱신 기준

사용자-facing 명령이나 workflow가 바뀌면 문서를 함께 갱신합니다.

| 변경 | 갱신할 문서 |
| --- | --- |
| 설치나 요구사항 변경 | `getting-started.md` |
| 사용 흐름 변경 | `usage.md` |
| CLI 옵션 변경 | `commands.md` |
| 데이터 흐름, 보안 모델 변경 | `architecture.md` |
| 개발 절차 변경 | `development.md` |
| 알려진 한계나 계획 변경 | `backlog.md` |

## 기여 전 체크리스트

```bash
pytest -v
ruff check src/ tests/
mypy src/synapse_memory
git diff
```

기능 변경 PR은 다음을 설명해야 합니다.

- 무엇이 바뀌었는지
- 어떤 테스트를 돌렸는지
- raw 데이터와 외부 LLM 경계가 안전한지
- 사용자가 직접 편집한 vault 파일을 덮어쓰지 않는지

## 라이선스

MIT
