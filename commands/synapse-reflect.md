---
description: Preview or apply reflection of an approved MemoryInbox candidate
argument-hint: <candidate_id>
---

# Synapse Memory Reflect

Use the candidate ID provided by the user.

Preview first:

```bash
python3 scripts/synapse.py reflect <candidate_id>
```

Only apply if:

- the MemoryInbox row status is already `approved`
- the user explicitly asks to apply

Apply:

```bash
python3 scripts/synapse.py reflect <candidate_id> --apply
```

Never change `Profile.md`, `DecisionPatterns.md`, or `DecisionQualityRegistry.md` without `--apply`.
