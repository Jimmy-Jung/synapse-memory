---
name: config
description: Use when the user wants to inspect or change Synapse Memory settings ("cleanup 임계값 60일로 늘려줘", "top-k 8로", "설정 검증해줘"). Edits ~/.synapse/config.yaml safely through explicit CLI subcommands.
---

# /sm:config — 사용자 설정 관리

`~/.synapse/config.yaml` 를 명시적 CLI subcommand로 조회/수정합니다. 직접 yaml 편집을
피하고 싶을 때 사용.

## 실행

```bash
synapse-memory config show
synapse-memory config show --json
synapse-memory config get <점 표기 키>
synapse-memory config set <점 표기 키> <값>
synapse-memory config validate
```

예시:

- `synapse-memory config set cleanup.inbox_stale_days 60`
- `synapse-memory config set top_k.ask 8`
- `synapse-memory config get hook.suggest_register`
- `synapse-memory config validate`

변경 전 현재 값을 `config get`으로 확인하고, 사용자 승인 후 `config set`으로 저장합니다.
