# Quickstart: Recipe Hybrid Retrieval

**Feature**: 008-recipe-hybrid-retrieval  
**Estimated time**: 5-10 minutes  
**Prerequisites**:

- 006 raw-rag-hybrid artifacts are present on the current branch.
- RAG optional dependencies are installed.
- A vault with ProjectCards and recipe support exists.

## 1. Prepare the hybrid sidecar

```bash
export SYNAPSE_FROM_AGENT=1
export SYNAPSE_OBSIDIAN_VAULT=/path/to/vault

synapse-memory rag index --include-raw --rebuild
```

Expected key stdout:

```text
인덱싱 시작 (rebuild=True, include_raw=True)
...
bm25=N
```

## 2. Mark a recipe as hybrid

Create or edit:

```text
$SYNAPSE_OBSIDIAN_VAULT/90_System/AI/recipes/hybrid_weekly.md
```

```markdown
---
name: hybrid_weekly
description: Hybrid weekly report smoke recipe
input_schema:
  period: required
rag_filter:
  source_kind: card_project
rag_top_k: 10
rag_mode: hybrid
use_profile: true
save_subpath: 30_Creative/Reports
locale_aware: true
domain_aware: true
timeout: 120
---

당신은 사용자의 주간 보고 작성 보조입니다.
{period} 기간의 관련 자료를 바탕으로 {locale} 보고서를 작성합니다.
모든 주장에 `[card_id]` 출처를 붙입니다.
```

## 3. Generate with recipe default hybrid mode

```bash
synapse-memory me generate hybrid_weekly --input period=2026-W19
```

Expected stderr:

```text
[me.generate.hybrid_weekly] source=user rag_mode=hybrid locale=... domain=... profile_used=True matched=... duration=...ms
```

Expected stdout:

```text
## ...

[saved] /path/to/vault/30_Creative/Reports/hybrid_weekly - 2026-W19 (...).md
```

## 4. Override to dense for comparison

```bash
synapse-memory me generate hybrid_weekly \
  --input period=2026-W19 \
  --rag-mode dense
```

Expected stderr includes:

```text
rag_mode=dense
```

## 5. Verify explicit hybrid error

Run in an isolated L0 root without BM25 sidecar:

```bash
tmp_l0=$(mktemp -d /tmp/synapse-hybrid-missing.XXXXXX)
SYNAPSE_L0_ROOT="$tmp_l0" \
SYNAPSE_FROM_AGENT=1 \
synapse-memory me generate hybrid_weekly --input period=2026-W19 --rag-mode hybrid
```

Expected stderr:

```text
rag_mode=hybrid requires BM25 sidecar
synapse-memory rag index --include-raw
```

The command must fail non-zero and must not silently fall back to dense.

Actual smoke captured on 2026-05-12 is in [quickstart-results.md](./quickstart-results.md).

## 6. Regression check

```bash
python3 -m pytest tests/test_endpoints_me.py tests/test_endpoints_me_extra.py
python3 -m pytest tests/test_recipes_loader.py tests/test_recipes_pipeline.py tests/test_recipes_cli.py tests/test_recipes_generate.py tests/test_recipes_domain.py
python3 -m pytest
```
