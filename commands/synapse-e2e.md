---
description: Run Synapse Memory local e2e fixture in a temporary workspace
---

# Synapse Memory E2E Fixture

Run:

```bash
python3 scripts/synapse.py e2e --dry-run
```

If the user wants a real local fixture run, execute:

```bash
python3 scripts/synapse.py e2e
```

The fixture must use a temporary workspace and must not write to the real Vault MemoryInbox.
