---
description: Bootstrap Synapse Memory local runtime directories on this Mac
---

# Synapse Memory Bootstrap

First run a dry-run:

```bash
python3 scripts/synapse.py bootstrap
```

Explain the planned local-only paths. Confirm that `~/.synapse/private` must not be synced to iCloud.

Only if the user explicitly asks to apply, run:

```bash
python3 scripts/synapse.py bootstrap --apply
```

Do not enable hooks or LaunchAgents from this command.
