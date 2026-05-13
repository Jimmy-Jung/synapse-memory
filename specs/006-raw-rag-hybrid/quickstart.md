# Quickstart: Raw RAG Hybrid

## 0. 환경 확인

```bash
synapse-memory doctor
python3 -m pytest tests/test_rag_indexer.py -q
```

## 1. Card-only baseline 인덱싱

```bash
synapse-memory rag index --rebuild
synapse-memory ask "샘플회사B 경험" --top-k 5
```

기대:

- Card 결과만 출처에 표시된다.
- raw path citation은 없어야 한다.

## 2. raw 포함 인덱싱

```bash
synapse-memory rag index --rebuild --include-raw
```

기대:

- 출력에 `raw_obsidian=<N>`, `raw_claude_code=<N>`, `bm25=<N>`이 표시된다.
- raw source가 없어도 command는 성공하고 count 0을 표시한다.

## 3. hybrid ask

```bash
synapse-memory ask "샘플회사B 경험" --hybrid --top-k 5
```

기대:

- 출처에 Card와 raw chunk가 함께 표시될 수 있다.
- raw chunk는 `raw_obsidian:<path>#<chunk>` 또는 `raw_claude_code:<path>#<chunk>` 형태로 인용된다.

## 4. hybrid recall

```bash
synapse-memory me what-did-i-think "이직 제안" --hybrid --top-k 8
```

기대:

- 기존 distance-mode recall 답변이 생성된다.
- 검색 근거 순서가 hybrid RRF 결과를 따른다.

## 5. prompt privacy smoke

테스트 fixture로 synthetic PII marker를 넣은 raw note를 만든 뒤 endpoint prompt capture 테스트를 실행한다.

```bash
python3 -m pytest tests/test_endpoints_ask.py::TestAsk::test_hybrid_prompt_uses_redacted_raw_context -q
```

기대:

- provider prompt에 원본 marker가 없어야 한다.
- redacted placeholder는 포함될 수 있다.

## 6. 검증 명령

```bash
python3 -m pytest tests/test_rag_chunker.py tests/test_rag_bm25.py tests/test_rag_hybrid.py tests/test_rag_indexer.py tests/test_endpoints_ask.py tests/test_endpoints_me_extra.py -q
uvx ruff check src/synapse_memory/rag src/synapse_memory/endpoints/ask.py src/synapse_memory/endpoints/me.py src/synapse_memory/cli.py tests/test_rag_chunker.py tests/test_rag_bm25.py tests/test_rag_hybrid.py tests/test_rag_indexer.py tests/test_endpoints_ask.py tests/test_endpoints_me_extra.py
python3 -m mypy --strict src/synapse_memory/rag src/synapse_memory/endpoints/ask.py src/synapse_memory/endpoints/me.py
python3 -m pytest tests/ -W ignore::DeprecationWarning
```

## 7. redaction eval

```bash
python3 -m synapse_memory.cli eval redaction --golden tests/golden/pii_synthetic.json
```

결과를 `specs/006-raw-rag-hybrid/redaction-eval-results.md`에 기록한다.
