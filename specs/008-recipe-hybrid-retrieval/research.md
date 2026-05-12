# Research: Recipe Hybrid Retrieval

**Feature**: 008-recipe-hybrid-retrieval  
**Date**: 2026-05-12

## R-1 — Where retrieval mode is declared

- **Decision**: Add optional `rag_mode` to recipe markdown frontmatter with allowed values `dense` and `hybrid`.
- **Rationale**: Recipe authors already declare `rag_filter`, `rag_top_k`, `locale_aware`, and `domain_aware` in frontmatter. Retrieval strategy is the same class of per-task policy.
- **Alternatives considered**:
  - Global config only: rejected because weekly reports, resume, journal, and brainstorm have different retrieval needs.
  - Separate recipe directory for hybrid variants: rejected because it duplicates prompts and makes user recipes harder to maintain.

## R-2 — Default behavior for existing recipes

- **Decision**: Missing `rag_mode` defaults to `dense`.
- **Rationale**: 007 shipped dense-only behavior. Existing user recipes must continue working without edits or sidecar prerequisites.
- **Alternatives considered**:
  - Default hybrid: rejected because BM25 sidecar may not exist and would break existing workflows.
  - Auto-select by recipe name: rejected because hidden policy is hard to test and document.

## R-3 — CLI override precedence

- **Decision**: `--rag-mode dense|hybrid` overrides recipe frontmatter for that invocation only.
- **Rationale**: Users need a quick comparison/debug path without editing vault recipe markdown. This mirrors existing CLI precedence for language/domain.
- **Alternatives considered**:
  - No override: rejected because smoke/debug requires file edits.
  - Persist override into recipe file: rejected because CLI should not mutate user-authored recipes.

## R-4 — Hybrid unavailable policy

- **Decision**: Fail explicitly when hybrid prerequisites are missing. Error text must include `synapse-memory rag index --include-raw`.
- **Rationale**: 006 policy rejects silent fallback. Users who asked for hybrid should not receive dense-only results labeled as hybrid.
- **Alternatives considered**:
  - Dense fallback with warning: rejected because downstream generated text can be trusted incorrectly.
  - Auto-run indexing: rejected because indexing is a batch operation with privacy/performance implications.

## R-5 — RRF k configurability

- **Decision**: Use 006 default RRF k=60. Do not expose recipe-level override.
- **Rationale**: This feature integrates an existing retrieval contract; tuning RRF per recipe would expand the state space and test matrix without current evidence.
- **Alternatives considered**:
  - `rag_rrf_k` frontmatter: rejected for first integration; can be added later if retrieval eval shows need.
  - CLI `--rrf-k`: rejected because it exposes ranking internals in a user workflow.

## R-6 — Matched-record interface for downstream pipeline

- **Decision**: Adapt hybrid `RetrievalHit` values into the same `list[(record, score)]` shape currently consumed by prompt composition, domain inference, source id extraction, and last_answer.
- **Rationale**: The recipe pipeline already has one downstream path. Keeping the interface stable limits the change to retrieval selection and prevents domain/profile/save behavior drift.
- **Alternatives considered**:
  - Introduce a second hybrid-specific context object: rejected because it duplicates prompt/citation logic.
  - Change all matched records to a new common type first: rejected as larger refactor than this integration needs.

## R-7 — Domain-aware interaction

- **Decision**: Hybrid results feed the existing tags-based domain inference unchanged.
- **Rationale**: Domain inference depends on matched record metadata, not retrieval algorithm. Hybrid may include raw chunks without tags; those simply do not contribute tags unless metadata provides them.
- **Alternatives considered**:
  - Infer domain from BM25 tokens: rejected because it would be a new heuristic and hard to validate.
  - Force domain to generic in hybrid mode: rejected because ProjectCard hybrid hits can still carry domain tags.

## R-8 — Redaction and privacy boundary

- **Decision**: Recipe hybrid mode must not read raw sources directly. It consumes only 006 hybrid results, which are expected to contain redacted documents.
- **Rationale**: Constitution Principle II is non-negotiable. Recipe pipeline should not become a second raw indexing or redaction owner.
- **Alternatives considered**:
  - Let recipe pipeline read raw notes for richer prompts: rejected as a privacy boundary violation and scope expansion.

## R-9 — Implementation dependency on 006 branch

- **Decision**: Treat 006 raw-rag-hybrid as an upstream dependency. If it is not present on the implementation branch, first merge/rebase onto 006 or land 006 into `main`.
- **Rationale**: Current `main` contains 007 but not 006. Reimplementing 006 in 008 would duplicate scope and muddy review boundaries.
- **Alternatives considered**:
  - Implement recipe hybrid against stubs only: rejected because integration tests would not verify real sidecar behavior.
  - Cherry-pick only `hybrid.py`: rejected because it depends on BM25/indexer contracts and tests.
