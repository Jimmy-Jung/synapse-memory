---
description: Show Synapse Memory plugin status and configured Vault/runtime paths
---

# Synapse Memory Status

Run:

```bash
python3 scripts/synapse.py status
```

Summarize whether `vault_ready` is true, list any missing files, and clearly distinguish:

- shared Vault path: `vault_ai_root`
- local runtime path: `runtime_root`
- local private path: `private_root`

Do not modify files.
