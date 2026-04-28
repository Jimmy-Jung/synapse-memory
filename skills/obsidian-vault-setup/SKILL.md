---
name: obsidian-vault-setup
description: Use when creating or initializing an Obsidian Vault folder structure for the Synapse method, including 00_Inbox, 10_Active, 20_Reference, 30_Creative, 40_Life, 90_System, 99_Archive, and optional 90_System/AI memory folders.
---

# Obsidian Vault Setup

## Purpose

Use this skill to initialize a Synapse-style Obsidian Vault structure.

Default structure:

```text
00_Inbox/
10_Active/
20_Reference/
30_Creative/
40_Life/
90_System/
99_Archive/
```

AI Memory structure:

```text
90_System/AI/
  MemoryInbox/
  Policies/
  Schemas/
  Scripts/
  Tests/
  Sessions/
  Prompts/
```

## Safety Rules

- Always dry-run first.
- Never delete, move, or rename existing user files.
- Do not overwrite existing notes unless the user explicitly asks for overwrite.
- Do not put raw AI conversations into the Vault.
- Keep `~/.synapse/private` outside iCloud/synced Vaults.

## Workflow

1. Identify the Vault root.
2. Run dry-run:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault"
```

3. Show the planned directories/files.
4. If the user approves, apply:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --apply
```

5. Verify resulting directories exist.

## Options

Without AI Memory folders:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --without-ai-memory
```

Custom author:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --author "Name"
```

Overwrite generated starter notes only when explicitly requested:

```bash
python3 scripts/synapse.py vault-setup --vault-root "/path/to/Vault" --apply --overwrite
```
