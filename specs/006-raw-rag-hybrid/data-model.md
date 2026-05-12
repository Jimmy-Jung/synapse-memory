# Data Model: Raw RAG Hybrid

## RawChunk

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | string | yes | `raw_obsidian:<hash>:<chunk_index>` or `raw_claude_code:<hash>:<chunk_index>` |
| `source_kind` | enum | yes | `raw_obsidian` or `raw_claude_code` |
| `path` | string | yes | User-visible relative path when possible |
| `chunk_index` | int | yes | Zero-based chunk position within source file |
| `text` | string | yes | Redacted chunk text only |
| `created` | string | no | File mtime ISO date/time when available |
| `display_name` | string | yes | Path basename or short citation label |

**Invariants**:

- `text` must not contain unredacted synthetic PII markers in tests.
- `id` is stable for unchanged path + chunk index.
- empty or whitespace-only `text` is not persisted.

## BM25Document

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `record_id` | string | yes | Same id as VectorRecord |
| `text` | string | yes | Redacted searchable document |
| `tokens` | list[string] | yes | Deterministic tokenizer output |
| `metadata` | object | yes | Citation metadata copied from VectorRecord |

**Storage**: `~/.synapse/private/rag/bm25.jsonl` with user-only permissions inherited from L0.

## RetrievalHit

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `record` | VectorRecord | yes | Unified retrieved document |
| `dense_rank` | int/null | no | 1-based rank from vector search |
| `dense_distance` | float/null | no | Smaller is better |
| `bm25_rank` | int/null | no | 1-based rank from BM25 |
| `bm25_score` | float/null | no | Larger is better |
| `rrf_score` | float | yes | Combined final score |

**Sort order**:

1. `rrf_score` descending
2. `bm25_score` descending, null last
3. `dense_distance` ascending, null last
4. `record.id` ascending

## IndexStats extension

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `project_cards` | int | yes | Existing count |
| `company_cards` | int | yes | Existing count |
| `raw_obsidian_chunks` | int | yes | New count |
| `raw_claude_code_chunks` | int | yes | New count |
| `bm25_documents` | int | yes | Number of sidecar docs written |
| `bytes_indexed` | int | yes | Redacted bytes indexed |
| `failed` | list[tuple] | yes | Stage/file failures |

## Citation label rules

- Card citations keep existing `card_id`.
- Raw Obsidian citations use `raw_obsidian:<relative-path>#<chunk_index>`.
- Raw Claude Code citations use `raw_claude_code:<relative-path>#<chunk_index>`.
- External AI prompts may include citation labels and redacted snippets, never full raw path content beyond path labels.
