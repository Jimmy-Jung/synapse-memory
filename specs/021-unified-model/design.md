# 021 — Unified Model Authoritative Design

Author: JunyoungJung
Created: 2026-07-06
Status: authoritative

This document is the source of truth for the post-redesign Synapse Memory
structure. It consolidates the current parts of 019, 020, and the completed
structural redesign. Older specs are historical context only.

## Current Shape

Synapse Memory is a local-first, provider-only personal wiki system:

1. Raw collectors mirror source material into local private storage.
2. A single Entity model stores wiki knowledge as Markdown with YAML
   frontmatter.
3. `src/synapse_memory/schema.yaml` is the single schema source for entity
   types, folders, per-type enum fields, statuses, and typed relations.
4. Ingest updates existing wiki pages instead of building a separate review
   queue or card layer.
5. Retrieval builds a lightweight in-memory page/entity index and asks the
   selected provider to choose relevant pages. Local embedding, vector, BM25,
   and hybrid retrieval paths are not part of the active design.
6. Lint is a validation layer plus the existing dead-link structural fixer. It
   emits a plain terminal/Markdown report and does not generate Obsidian MOCs
   or review queues.

## Filesystem Contract

Entity files live under schema-declared folders:

| Type | Folder | Notes |
| --- | --- | --- |
| `project` | `Entities/Projects/` | project truth source |
| `company` | `Entities/Companies/` | company and application context |
| `concept` | `Concepts/` | technologies, decisions, reusable ideas |
| `insight` | `Insights/YYYY/MM/` | answers and synthesized observations |
| `log` | `Logs/YYYY/MM/` | time-bound activity records |
| `profile` | `Profile/` | user facts and durable preferences |

Every entity page requires `type`, `slug`, `title`, and `status`. The `slug`
must match the filename without `.md`; the file path must match the folder for
its `type`. Status values and typed attributes are validated from
`schema.yaml`.

## Entity Model

The active model is `synapse_memory.model.Entity`.

Common fields stay top-level:

- `type`
- `slug`
- `title`
- `status`
- `created`
- `updated`
- `observed_at` for `insight` and `log`
- `sources`

Type-specific fields live in `attrs` and serialize as normal frontmatter keys.
The old `ProjectCard`, `CompanyCard`, and `InsightCard` surfaces remain as
compatibility adapters over Entity. They are not separate persistence models.

## Typed Relations

Typed relation keys are declared by `schema.yaml`:

- `uses`
- `part_of`
- `about`
- `decided_in`
- `supersedes`
- `same_as`

Relation values may be `[[slug]]`, `type:slug`, or plain `slug`. Lint resolves
the target slug against current entity pages and checks both schema
`domain` and `range`. For example, `uses` currently points to `concept`, so a
page that `uses: [[some-company]]` is invalid when `some-company` is a
`company`.

## Ingest

The active ingest path is unified:

```text
collect raw -> build page index -> select related pages -> integrate -> write entity pages -> lint
```

The integration prompt and JSON schema live in
`src/synapse_memory/wiki/integration.py`. Agent-facing schema guidance is
generated from `schema.yaml` and embedded into `INTEGRATION_SYSTEM`; there is
no separate `SCHEMA.md` file to keep in sync.

## Retrieval

Provider-only retrieval is the active retrieval contract:

- `build_page_index()` / entity index code builds a small deterministic index
  from Markdown pages.
- `select_related()` asks the configured provider to choose relevant slugs.
- Ask/persona/recipe flows use those selected pages as context.

The design intentionally avoids a resident local ML process. Bounded,
short-lived jobs are preferred so memory is released by process exit.

## Lint

`synapse-memory lint --now` runs:

1. `apply_structural_fixes()` to remove dead `related` links. This legacy
   autofix stays intentionally narrow and idempotent.
2. Schema validation:
   - required frontmatter fields
   - enum values from `schema.yaml`
   - type-to-folder consistency
   - slug-to-filename consistency
   - relation domain/range and missing target checks
   - index freshness when an index page declares a total page count

Output is plain text suitable for terminal logs or Markdown paste. Lint does
not write Obsidian-specific review queues and does not generate MOC files.

## Historical Specs

Only these specs are current at the repository top level:

- `019-llm-wiki-redesign`
- `020-provider-only-retrieval`
- `021-unified-model`

All earlier specs are archived under `specs/_historical/` and should not be
used as implementation source of truth unless a future plan explicitly revives
one.
