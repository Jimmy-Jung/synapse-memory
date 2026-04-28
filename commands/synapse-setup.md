---
description: Unified Synapse Memory onboarding — guided install and first-use, with explicit approval at every apply step
---

# Synapse Memory Setup

This is the single entry point for installing and starting to use Synapse Memory. It runs each phase as dry-run first, asks the user before applying, and never bundles auto-execution with installation.

Invoke the `synapse-setup` skill and follow its onboarding flow. Do not skip steps. Do not chain `--apply` calls without per-step approval.

## Sequence

1. `python3 scripts/synapse.py status` — report `vault_ai_root`, `runtime_root`, `private_root`, `vault_ready`. If the Vault path is wrong, ask the user for the real path and use `SYNAPSE_VAULT_AI_ROOT` or `--vault-ai-root` from this point on.

2. If the Vault has no Synapse folder layout:

   ```bash
   python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault"
   ```

   Show planned directories. Apply only after explicit approval:

   ```bash
   python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --apply
   ```

3. If `~/.synapse` runtime is missing:

   ```bash
   python3 scripts/synapse.py bootstrap
   ```

   Show planned local-only paths. Apply only after explicit approval:

   ```bash
   python3 scripts/synapse.py bootstrap --apply
   ```

4. Hook + LaunchAgent install:

   ```bash
   python3 scripts/synapse.py install
   ```

   Summarize hook script path, 4 LaunchAgent plists, `settings.json` diff, and resolved `vault_ai_root`. Apply only after explicit approval:

   ```bash
   python3 scripts/synapse.py install --install
   ```

   `--load-agents` (auto-execution ON) is a separate decision. Run it only if the user separately confirms:

   ```bash
   python3 scripts/synapse.py install --install --load-agents
   ```

5. End-to-end fixture in a temp workspace (never touches the real Vault):

   ```bash
   python3 scripts/synapse.py e2e --dry-run
   ```

6. On success, print the daily-use summary:

   ```text
   /synapse-memory:synapse-review
   Edit MemoryInbox/YYYY-MM-DD.md  -> set Status to "approved"
   /synapse-memory:synapse-reflect <MC-ID>
   /synapse-memory:synapse-reflect <MC-ID> --apply
   ```

## Hard Rules

- Never auto-approve memory candidates.
- Never apply two phases in a single turn without separate approval for each.
- Never move `~/.synapse/private` into a synced location.
- Never write raw conversation data into `90_System/AI`.
- If `e2e --dry-run` fails, stop and diagnose. Do not declare setup complete.
