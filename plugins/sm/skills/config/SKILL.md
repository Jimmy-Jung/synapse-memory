---
name: config
description: Use when the user wants to change Synapse Memory settings in natural language ("cleanup 임계값 60일로 늘려줘", "모델 sonnet으로 바꿔", "top-k 8로", "자동화 켜줘"). Edits ~/.synapse/config.yaml safely.
---

# /sm:config — 사용자 설정 관리

`~/.synapse/config.yaml` 를 자연어로 수정합니다. 직접 yaml 편집을 피하고 싶을 때 사용.

## 실행

```bash
synapse-memory config
synapse-memory config "<자연어 변경 지시>"
```

예시:

- `synapse-memory config "cleanup inbox 60일로"`
- `synapse-memory config "ask top-k 8"`
- `synapse-memory config "모델 claude-sonnet-4-6"`

변경 전 diff 를 사용자에게 보여주고, 승인 후 저장합니다.
