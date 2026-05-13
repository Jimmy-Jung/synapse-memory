# CLI Contracts: Raw RAG Hybrid

## `synapse-memory rag index`

```bash
synapse-memory rag index [--rebuild] [--include-raw]
```

### Options

| Option | Behavior |
|---|---|
| `--rebuild` | Clears vector collection before indexing. Existing behavior. |
| `--include-raw` | Adds redacted raw chunks from vault `10_Active/` and L0 `redacted/claude-code/` to Card vectors and writes BM25 sidecar. |

### Success output

```text
인덱싱 완료: project=1 company=1 raw_obsidian=3 raw_claude_code=2 bm25=7 bytes=12345
총 벡터: 7
```

### Failure output

- Embedding unavailable: exit code 2.
- Vector/BM25 storage unavailable: exit code 2.
- Redaction failure for raw chunk: exit code 1 and failed file/stage listed.

## `synapse-memory ask`

```bash
synapse-memory ask "<query>" [--top-k N] [--model MODEL] [--kind project|company] [--hybrid]
```

### Options

| Option | Behavior |
|---|---|
| `--hybrid` | Uses dense vector + BM25 RRF(k=60) retrieval. Requires BM25 sidecar. |
| `--kind` with `--hybrid` | Limits Card results to selected Card kind and excludes raw chunks from that filtered query. |

### Source output

Dense-only keeps current distance format. Hybrid output may include RRF/BM25 details:

```text
출처 (3):
  [0.032] card_company   examplecorp — 샘플회사B
  [0.029] raw_obsidian   10_Active/학습.md#0 — 학습.md
```

## `synapse-memory me what-did-i-think`

```bash
synapse-memory me what-did-i-think "<topic>" [--top-k N] [--model MODEL] [--hybrid]
```

### Options

| Option | Behavior |
|---|---|
| `--hybrid` | Uses dense + BM25 RRF retrieval for the distance-mode recall prompt. |
| `--timeline` + `--hybrid` | Out of scope for this feature. CLI must reject this combination or keep timeline behavior unchanged with a clear message. |

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Command completed successfully. |
| 1 | Runtime failure after dependencies were available, including redaction failure. |
| 2 | Missing local dependency, unavailable vector/BM25 store, invalid CLI combination, or AI provider unavailable. |
