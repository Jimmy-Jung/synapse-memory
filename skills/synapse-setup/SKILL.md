---
name: synapse-setup
description: Use as the single entry point to install and start using Synapse Memory. Walks the user through a dry-run-first onboarding (status -> Vault structure -> local runtime -> Claude hook + LaunchAgent -> e2e fixture) with explicit approval at every apply step, then prints daily-use commands. Use this when the user says "install", "set up", "first time", "start using", or "how do I begin" with Synapse Memory.
---

# Synapse Memory Setup (Unified Onboarding)

## Purpose

Be the one skill a new user needs. Guide them from a fresh machine to a working Synapse Memory pipeline without forcing them to learn six separate commands first.

This skill orchestrates the existing CLI. It does not replace `synapse-memory` or `obsidian-vault-setup` skills — those remain for deep-dive operations.

## Core Rules (Non-Negotiable)

- Every `--apply` / `--install` / `--load-agents` step requires explicit user approval in the same turn. Never chain applies.
- Always run dry-run first and surface the diff/plan before asking for approval.
- `~/.synapse/private` is local-only. Never suggest moving it to iCloud, Dropbox, Git, or an Obsidian Vault.
- Raw or near-raw conversation data must never be written under `90_System/AI`.
- `reflect --apply` runs only after the user has manually flipped a candidate's `Status` to `approved` in `MemoryInbox/YYYY-MM-DD.md`.
- `--load-agents` (auto-execution switch) requires a separate, explicit confirmation distinct from `--install`.

## Onboarding Flow

Follow these steps in order. After each apply step, show the result and ask before moving on.

### Step 1 — Status Check

```bash
python3 scripts/synapse.py status
```

Read the JSON output. Report to the user:

- `vault_ai_root` (shared Vault path)
- `runtime_root` (local `~/.synapse`)
- `private_root` (local-only data)
- `vault_ready` (true/false)
- Any missing files

If `vault_ai_root` does not match the user's Obsidian Vault, ask for the real Vault path and either:

- export `SYNAPSE_VAULT_AI_ROOT="/path/to/Vault/90_System/AI"` for this session, or
- pass `--vault-ai-root "/path/to/Vault/90_System/AI"` to subsequent commands.

### Step 2 — Vault Structure (only if missing)

If the Vault has no `00_Inbox / 10_Active / 20_Reference / 30_Creative / 40_Life / 90_System / 99_Archive` layout, dry-run the setup:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault"
```

Show the planned directories. Apply only after explicit approval:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --apply
```

If the Vault already has the structure, skip this step.

### Step 3 — Local Runtime Bootstrap (only if missing)

Dry-run:

```bash
python3 scripts/synapse.py bootstrap
```

List the planned `~/.synapse/...` paths and remind the user these stay local. Apply only after explicit approval:

```bash
python3 scripts/synapse.py bootstrap --apply
```

### Step 4 — Claude Hook + LaunchAgent (the actual automation)

Dry-run:

```bash
python3 scripts/synapse.py install
```

Summarize:

- `SessionEnd` hook script path
- LaunchAgent plist paths (4)
- `~/.claude/settings.json` change preview
- resolved `vault_ai_root`

Apply only after explicit approval:

```bash
python3 scripts/synapse.py install --install
```

If — and only if — the user separately confirms "turn on auto-execution", run:

```bash
python3 scripts/synapse.py install --install --load-agents
```

Treat `--load-agents` as a second decision. Do not bundle it with `--install`.

### Step 5 — End-to-End Fixture

```bash
python3 scripts/synapse.py e2e --dry-run
```

This uses a temp workspace and never writes to the real `MemoryInbox`. Confirm the fixture passes before declaring setup complete.

### Step 6 — Daily-Use Summary

Print this to the user once setup succeeds:

```text
Daily use:
  /synapse-memory:synapse-review            # check candidates (no auto-approve)
  Edit MemoryInbox/YYYY-MM-DD.md            # flip Status to "approved" manually
  /synapse-memory:synapse-reflect <MC-ID>   # preview
  /synapse-memory:synapse-reflect <MC-ID> --apply   # write to long-term memory

Health checks:
  python3 scripts/synapse.py kpi --dry-run
  python3 scripts/synapse.py archive --dry-run

Rollback:
  ~/.synapse/bin/rollback.sh --dry-run
  ~/.synapse/bin/rollback.sh
```

## Decision Tree (Quick Reference)

```text
status -> vault_ready?
  no  -> ask Vault path -> vault-setup (dry-run -> apply)
  yes -> next
runtime exists?
  no  -> bootstrap (dry-run -> apply)
  yes -> next
hook installed?
  no  -> install (dry-run -> --install)
  yes -> next
auto-execution wanted?
  yes (separate confirm) -> install --install --load-agents
  no  -> skip
e2e --dry-run -> success?
  yes -> print Daily-Use Summary
  no  -> diagnose, do not mark setup complete
```

## When to Defer to Other Skills

- Deep MemoryInbox review semantics, reflection rules, plugin packaging → `synapse-memory` skill.
- Full Vault folder taxonomy, sub-folder rationale → `obsidian-vault-setup` skill.
- Recurring KPI / archive / rollback operations → run the CLI directly; this skill is for first-time setup, not maintenance.

## Failure Modes

- `vault_ready=false` after Step 2 apply → re-run `status` with the correct `--vault-ai-root`; the user likely picked a different Vault path than the configured default.
- `install` dry-run shows an unexpected `settings.json` diff → stop and show the diff to the user before any apply.
- `e2e` fixture fails → do not proceed to install LaunchAgents; report the failing stage and stop.
