---
description: Dry-run or install Synapse Memory Claude hooks and LaunchAgents
---

# Synapse Memory Install

Start with:

```bash
python3 scripts/synapse.py install
```

This is a dry-run. Summarize:

- hook script path
- LaunchAgent plist paths
- target `settings.json`
- `vault_ai_root`

Only if the user explicitly asks to install, run:

```bash
python3 scripts/synapse.py install --install
```

Only if the user explicitly asks to load agents too, run:

```bash
python3 scripts/synapse.py install --install --load-agents
```

Never load LaunchAgents implicitly.
