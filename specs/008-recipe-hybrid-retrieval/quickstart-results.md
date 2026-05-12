# Quickstart Smoke Results: Recipe Hybrid Retrieval

**Feature**: 008-recipe-hybrid-retrieval
**Author**: JunyoungJung <joony300@gmail.com>
**Date**: 2026-05-12
**Machine**: local workstation, isolated fixture vault copied from `tests/fixtures/recipes_vault`
**Invocation**: `PYTHONPATH=src SYNAPSE_FROM_AGENT=1 python3 -m synapse_memory.cli ...`

## Fixture

- Vault copy: `/tmp/synapse-008-smoke.lgyMnk/vault`
- Built-in recipe checked: `weekly_report`
- User recipe added during smoke: `90_System/AI/recipes/hybrid_weekly.md`
- Missing-sidecar check used isolated L0 root: `/tmp/synapse-008-missing-l0.ZevtUU`

## `me recipes list`

Command:

```bash
python3 -m synapse_memory.cli me recipes list --vault "$VAULT"
```

Key stdout:

```text
NAME           SOURCE   REQUIRED INPUTS  DESCRIPTION
brainstorm     builtin  topic            주제에 대한 발산형 아이디어 — 사용자 voice + 관련 카드 기반
diary          user     -                사용자 정의 — 오늘 vault 활동을 일기 톤으로 짧게 정리 (override 검증용)
weekly_report  builtin  period           주간 보고 — ProjectCard 활동과 사용자 voice 기반
```

stderr: empty.

## `me recipes show weekly_report`

Command:

```bash
python3 -m synapse_memory.cli me recipes show weekly_report --vault "$VAULT"
```

Key stdout:

```text
name:           weekly_report
source:         builtin
input_schema:
  - period (required)
  - audience (optional)
rag_filter:     {'source_kind': 'card_project'}
rag_top_k:      10
domain_aware:   False
model:          sonnet
```

stderr: empty.

## Dense Dry Run

Command:

```bash
python3 -m synapse_memory.cli me generate weekly_report \
  --input period=2026-W19 \
  --vault "$VAULT" \
  --dry-run
```

Key stdout:

```text
# DRY-RUN PREVIEW for recipe 'weekly_report'

## system prompt
입력 period(2026-W19) 에 해당하는 사용자의 ProjectCard 활동과 사용자 Profile
```

Key stderr:

```text
[me.generate.weekly_report] source=builtin rag_mode=dense locale=profile:한국어 domain=default:generic profile_used=True matched=10 duration=12556ms
```

Note: first local embedding load also emitted Hugging Face model loading progress before the observability line.

## User Hybrid Recipe Recognition

Added recipe:

```text
$VAULT/90_System/AI/recipes/hybrid_weekly.md
```

Command:

```bash
python3 -m synapse_memory.cli me recipes show hybrid_weekly --vault "$VAULT"
```

Key stdout:

```text
name:           hybrid_weekly
source:         user
description:    Hybrid weekly report smoke recipe
input_schema:
  - period (required)
rag_filter:     {'source_kind': 'card_project'}
rag_top_k:      10
domain_aware:   True
model:          sonnet
```

stderr: empty.

## Hybrid Dry Run

Command:

```bash
python3 -m synapse_memory.cli me generate hybrid_weekly \
  --input period=2026-W19 \
  --vault "$VAULT" \
  --dry-run
```

Exit code: `0`

Key stdout:

```text
# DRY-RUN PREVIEW for recipe 'hybrid_weekly'

## system prompt
2026-W19 기간의 관련 자료를 바탕으로 한국어 보고서를 작성합니다.
```

Key stderr:

```text
[me.generate.hybrid_weekly] source=user rag_mode=hybrid locale=profile:한국어 domain=profile:software profile_used=True matched=10 duration=12568ms
```

## Missing BM25 Sidecar

Command:

```bash
SYNAPSE_L0_ROOT="$MISSING_L0" python3 -m synapse_memory.cli me generate hybrid_weekly \
  --input period=2026-W19 \
  --vault "$VAULT" \
  --dry-run
```

Exit code: `10`

Key stderr:

```text
✗ rag_mode=hybrid requires BM25 sidecar. Run `synapse-memory rag index --include-raw` and retry.
```

Result: command failed explicitly and did not silently fall back to dense.
