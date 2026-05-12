# Data Model: Recipe Hybrid Retrieval

**Feature**: 008-recipe-hybrid-retrieval  
**Date**: 2026-05-12

## GenerationRecipe

Existing in-memory representation of one recipe markdown file.

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `rag_mode` | `"dense" | "hybrid"` | No | Defaults to `dense`; invalid values reject only that recipe. |

Existing fields such as `rag_filter`, `rag_top_k`, `domain_aware`, `use_profile`, and `save_subpath` keep their current meaning.

## EffectiveRetrievalMode

Resolved retrieval mode for one `generate()` invocation.

Resolution order:

1. CLI/library override (`--rag-mode`, `rag_mode_override`)
2. Recipe frontmatter `rag_mode`
3. Default `dense`

Validation:

- Only `dense` and `hybrid` are valid.
- Override is transient and never mutates the recipe markdown.

## GenerationContext

Runtime state for one recipe execution.

| Field | Type | Meaning |
| --- | --- | --- |
| `rag_mode` | `"dense" | "hybrid"` | Effective retrieval mode used for the invocation. |
| `matched_records` | `list[(VectorRecord-like, float)]` | Downstream-compatible matched records from dense or adapted hybrid retrieval. |

The rest of the context construction order remains:

```text
inputs validate → profile → locale → retrieval → domain → render → invoke/save/last_answer
```

## HybridMatchedRecord Adapter

Adapter from 006 `RetrievalHit` to recipe pipeline matched records.

Mapping:

| 006 `RetrievalHit` | Recipe matched record |
| --- | --- |
| `hit.record` | `record` |
| `hit.rrf_score` | score/distance slot, represented so prompt formatting remains deterministic |
| `hit.record.metadata` | preserved for `card_id`, `source_kind`, `display_name`, `domains`, `keywords`, `tags` |
| `hit.record.document` | redacted context text for prompt composition |

Validation:

- Metadata required for source ids and citations must not be dropped.
- Raw unredacted source text must never be introduced by the adapter.

## HybridAvailabilityError

User-facing failure state for hybrid mode when the BM25 sidecar or 006 dependency is unavailable.

Required message content:

- The failed mode: `rag_mode=hybrid`
- The missing prerequisite in plain language
- Remediation command: `synapse-memory rag index --include-raw`

The error must propagate to CLI as non-zero and must not be converted to dense results.

## State Transitions

```text
Recipe markdown saved
  → loader parses optional rag_mode
  → registry exposes recipe
  → generate resolves effective mode
  → dense mode: existing store.query path
  → hybrid mode: 006 hybrid_search path
  → matched records normalized
  → domain/profile/prompt/save/last_answer continue unchanged
```

## Backward Compatibility

- Recipes without `rag_mode` behave as dense.
- Existing saved output filenames are unchanged.
- Existing `last_answer.command` remains `me.generate.<recipe>`.
- Timeline recall bypass remains outside this data model.
