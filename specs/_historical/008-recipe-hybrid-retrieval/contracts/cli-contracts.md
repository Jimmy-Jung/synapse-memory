# CLI Contracts: Recipe Hybrid Retrieval

**Feature**: 008-recipe-hybrid-retrieval  
**Date**: 2026-05-12

## `synapse-memory me generate <recipe> [--rag-mode dense|hybrid]`

Classification: interactive endpoint under Constitution Principle IV. Existing TTY guard and `SYNAPSE_FROM_AGENT=1` bypass remain unchanged.

### Arguments

```bash
synapse-memory me generate weekly_report \
  --input period=2026-W19 \
  --rag-mode hybrid
```

| Argument | Required | Behavior |
| --- | --- | --- |
| `<recipe>` | Yes | Existing recipe name lookup. |
| `--input KEY=VALUE` | Per recipe | Existing input schema behavior. |
| `--rag-mode dense|hybrid` | No | Overrides recipe frontmatter for one invocation only. |

### Retrieval Mode Resolution

```text
CLI --rag-mode
  → recipe frontmatter rag_mode
  → dense
```

### Success Output

stdout remains generated markdown plus optional saved path.

stderr observability line appends effective mode:

```text
[me.generate.weekly_report] source=builtin rag_mode=hybrid locale=profile:한국어 domain=tags:software profile_used=True matched=4 duration=2841ms
```

### Error Output

Invalid CLI mode:

```text
usage: synapse-memory me generate ... --rag-mode {dense,hybrid}
```

Hybrid unavailable:

```text
✗ rag_mode=hybrid requires BM25 sidecar. Run `synapse-memory rag index --include-raw` and retry.
```

Exit codes:

| Case | Exit |
| --- | --- |
| Success | `0` |
| Invalid CLI argument | argparse non-zero |
| Recipe not found | existing `2` |
| Input validation | existing `3` |
| Recipe validation | existing `4` |
| Embedding / AI / hybrid retrieval unavailable | existing non-zero error path, with explicit stderr |

## Recipe Frontmatter Contract

```markdown
---
name: weekly_report
description: 주간 보고
input_schema:
  period: required
rag_filter:
  source_kind: card_project
rag_top_k: 10
rag_mode: hybrid
use_profile: true
locale_aware: true
domain_aware: true
---
```

Allowed values:

- `dense`
- `hybrid`

Missing field:

- Equivalent to `rag_mode: dense`

Invalid field:

- Loader rejects that recipe only.
- Registry still loads other valid recipes.
