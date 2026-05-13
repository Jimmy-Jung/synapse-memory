# File Contracts: Raw RAG Hybrid

## BM25 sidecar

**Path**: `~/.synapse/private/rag/bm25.jsonl`  
**Permissions**: parent L0 directory must be `0700`; file should be user-readable/writeable only.

Each line is one JSON object:

```json
{
  "record_id": "raw_obsidian:abc123:0",
  "text": "redacted searchable text",
  "tokens": ["redacted", "searchable", "text"],
  "metadata": {
    "source_kind": "raw_obsidian",
    "path": "10_Active/example.md",
    "chunk_index": 0,
    "display_name": "example.md",
    "created": "2026-05-12T09:00:00"
  }
}
```

### Prohibited fields/content

- raw prompt
- raw response
- unredacted note body
- unredacted Claude Code message body
- API key/OAuth token
- absolute private home path when a relative path is available

## Raw chunk vector metadata

VectorRecord metadata for raw chunks:

```json
{
  "source_kind": "raw_obsidian",
  "path": "10_Active/example.md",
  "chunk_index": 0,
  "display_name": "example.md",
  "created": "2026-05-12T09:00:00"
}
```

`card_id` is absent for raw chunks. Endpoint code must fall back to `record.id` or `path#chunk`.

## Retrieval eval fixture

**Path**: `tests/golden/raw_rag_hybrid/synthetic_queries.json`

```json
[
  {
    "query": "샘플회사B 경험",
    "target_id": "card_company:examplecorp",
    "dense_rank": 3,
    "bm25_rank": 1
  }
]
```

The fixture is synthetic and deterministic. PR notes must state that it is not real-world retrieval validation.
