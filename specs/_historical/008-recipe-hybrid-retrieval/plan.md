# Implementation Plan: Recipe Hybrid Retrieval

> **SUPERSEDED_BY_PROVIDER_ONLY / HISTORICAL ONLY**
>
> 이 문서는 provider-only 전환 전의 과거 구현 계획입니다. 현재 recipe/persona/ask
> 검색은 local hybrid ranking이 아니라 CardIndex + provider 선별 경로를 사용합니다.
> 현재 source of truth는 `specs/020-provider-only-retrieval/design.md`입니다.

**Branch**: `008-recipe-hybrid-retrieval` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/008-recipe-hybrid-retrieval/spec.md`

## Summary

Extend 007 recipe generation so each recipe can declare `rag_mode: dense | hybrid`, with CLI override via `--rag-mode`. Dense remains the default and preserves existing behavior. Hybrid mode delegates to the 006 raw-rag-hybrid contract, adapts `RetrievalHit` results into the recipe pipeline's existing matched-record shape, emits an explicit error when BM25 sidecar prerequisites are missing, and keeps domain-aware tag inference unchanged.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: existing `PyYAML`, `chromadb`, `sentence-transformers`, 006 `rank-bm25` hybrid stack, pytest  
**Storage**: existing vault recipe markdown; existing L0 vector/BM25 stores from 006 (`~/.synapse/private/rag/chroma/`, BM25 sidecar)  
**Testing**: pytest, recipe CLI/pipeline tests, endpoint regression tests, full `python3 -m pytest`  
**Target Platform**: macOS 26 Tahoe + Apple Silicon, local CLI/library  
**Project Type**: Python CLI/library  
**Performance Goals**: dense mode unchanged; hybrid mode adds no more than 006 hybrid retrieval overhead; `me recipes list` remains ≤ 1s for 50 recipes  
**Constraints**: Test-first implementation, no silent dense fallback, RRF k fixed at 60, external LLM receives redacted context only, timeline path remains outside recipe pipeline  
**Scale/Scope**: single-user local vault; built-in and user recipes; top-k 1-50 as already bounded by recipe loader

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate Result | Rationale / Mitigation |
| --- | --- | --- |
| I. Local-First & Privacy by Default | PASS | Feature only chooses between existing local dense store and 006 local hybrid sidecar. No new remote storage or network path. |
| II. Two-Pass Redaction | PASS with dependency | Hybrid mode relies on 006's redacted raw/BM25 contract. Tasks must include prompt-capture tests proving unredacted raw markers do not reach `ai_api_complete`. |
| III. Test-First Discipline | PASS | Tasks are RED -> GREEN ordered: loader/CLI/pipeline/domain/error tests before implementation. |
| IV. Conversation-Context-Aware Endpoints | PASS | `me generate` remains interactive and guarded at CLI layer; `me recipes list/show` remain batch. No new endpoint class. |
| V. Reproducible Daily Pipeline & Observability | PASS | `daily` is not changed. `me generate` observability is extended with effective `rag_mode` only. |

**Important dependency check**: current `main` does not contain `specs/006-raw-rag-hybrid/` or `src/synapse_memory/rag/hybrid.py`. Implementation must first land 006 on `main`, or rebase/merge this branch onto `006-raw-rag-hybrid`. This plan treats 006 as an upstream dependency and does not duplicate its raw indexing/BM25 implementation.

## Project Structure

### Documentation (this feature)

```text
specs/008-recipe-hybrid-retrieval/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/synapse_memory/
├── recipes/
│   ├── recipe.py          # GenerationRecipe / context / result retrieval-mode fields
│   ├── loader.py          # frontmatter validation for rag_mode
│   ├── pipeline.py        # dense vs hybrid retrieval selection and adaptation
│   └── builtin/
│       └── weekly_report.md
├── cli.py                 # me generate --rag-mode argument and observability
└── rag/
    └── hybrid.py          # upstream 006 dependency, not reimplemented here

tests/
├── test_recipes_loader.py
├── test_recipes_pipeline.py
├── test_recipes_cli.py
├── test_recipes_domain.py
├── test_recipes_generate.py
└── test_endpoints_me*.py
```

**Structure Decision**: Keep retrieval policy inside `synapse_memory.recipes` because recipe declarations own the opt-in. Keep dense/hybrid ranking implementation inside `synapse_memory.rag`; recipe pipeline only resolves mode, builds the query, calls the selected retriever, and adapts results to the existing matched-record interface.

## Phase 0 산출물

See [research.md](./research.md).

## Phase 1 산출물

- [data-model.md](./data-model.md)
- [contracts/cli-contracts.md](./contracts/cli-contracts.md)
- [quickstart.md](./quickstart.md)

## Constitution Check (post-design re-check)

| Principle | Result |
| --- | --- |
| I. Local-First & Privacy by Default | PASS. No new non-local persistence or remote boundary. |
| II. Two-Pass Redaction | PASS with explicit tests. Hybrid mode consumes 006 redacted records and adds no raw source read path. |
| III. Test-First Discipline | PASS. tasks.md starts each behavior slice with failing tests. |
| IV. Conversation-Context-Aware Endpoints | PASS. Existing endpoint classification unchanged. |
| V. Reproducible Daily Pipeline & Observability | PASS. `daily` unchanged; `me generate` one-line stderr gains `rag_mode=<mode>`. |

**Final gate result**: PASS. Complexity Tracking not required.

## Complexity Tracking

No constitutional violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
