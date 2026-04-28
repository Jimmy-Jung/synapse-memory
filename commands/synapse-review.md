---
description: Review MemoryInbox candidates without automatic approval
---

# Synapse Memory Review

Run:

```bash
python3 scripts/synapse.py review --dry-run
```

Summarize:

- reviewed count
- pending count
- expired count
- changed count

Do not approve candidates. The reviewer may only move expired pending candidates to `expired` when run without dry-run.
