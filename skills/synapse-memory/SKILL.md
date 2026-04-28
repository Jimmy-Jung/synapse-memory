---
name: synapse-memory
description: Use when installing, configuring, reviewing, testing, or explaining the Synapse Memory local-first AI memory pipeline for Claude/Codex and Obsidian MemoryInbox workflows.
---

# Synapse Memory Skill

## Purpose

Use this skill for Synapse Memory operations:

- bootstrap a new Mac
- install or dry-run Claude hooks and LaunchAgents
- run local e2e fixture checks
- review MemoryInbox candidates
- reflect approved candidates into long-term memory
- explain the local/private boundary
- maintain Claude/Codex plugin packaging compatibility

## Plugin Compatibility

This repository is packaged for both Claude Code and Codex:

```text
.claude-plugin/plugin.json
.claude-plugin/marketplace.json
.codex-plugin/plugin.json
commands/
skills/synapse-memory/SKILL.md
skills/obsidian-vault-setup/SKILL.md
scripts/synapse.py
```

Claude Code uses `.claude-plugin/` and `commands/`.
Codex uses `.codex-plugin/` and `skills/`.

Keep both manifests in sync when changing name, version, description, or repository metadata.

## Safety Rules

- Never move `~/.synapse/private` into iCloud or a synced Vault.
- Never write raw or near-raw conversation data into `90_System/AI`.
- Never auto-approve memory candidates.
- Only reflect candidates whose `Status` is already `approved`.
- Use dry-run first for install, review, e2e, KPI, and archive commands.

## Common Commands

```bash
python3 scripts/synapse.py status
python3 scripts/synapse.py bootstrap
python3 scripts/synapse.py bootstrap --apply
python3 scripts/synapse.py install
python3 scripts/synapse.py e2e --dry-run
python3 scripts/synapse.py review --dry-run
python3 scripts/synapse.py kpi --dry-run
python3 scripts/synapse.py archive --dry-run
```

Preview a reflection:

```bash
python3 scripts/synapse.py reflect MC-YYYYMMDD-A-NNN
```

Apply a reflection only after the MemoryInbox row is manually marked `approved`:

```bash
python3 scripts/synapse.py reflect MC-YYYYMMDD-A-NNN --apply
```

## Bootstrap Workflow

1. Run `synapse.py bootstrap`.
2. Confirm the target paths are local-only.
3. Run `synapse.py bootstrap --apply`.
4. Run `synapse.py install` for hook/LaunchAgent dry-run.
5. Run `synapse.py e2e --dry-run`.

## Vault Selection

By default the plugin expects:

```text
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/90_System/AI
```

For another Vault, pass:

```bash
python3 scripts/synapse.py status --vault-ai-root "/path/to/90_System/AI"
```

or set:

```bash
export SYNAPSE_VAULT_AI_ROOT="/path/to/90_System/AI"
```

## Source of Truth

Shared memory lives in the Obsidian Vault:

```text
90_System/AI/MemoryInbox/
90_System/AI/Profile.md
90_System/AI/DecisionPatterns.md
90_System/AI/DecisionQualityRegistry.md
```

Machine-local runtime state lives here:

```text
~/.synapse/private/
```
