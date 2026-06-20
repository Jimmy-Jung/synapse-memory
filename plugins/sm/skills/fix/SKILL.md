---
name: fix
description: Use when the user says "설치가 깨졌어 / 고쳐줘", "synapse-memory 안 돼", "doctor 실패난 거 자동으로 고쳐줘". Applies only whitelisted repair actions (no destructive ops).
---

# /sm:fix — 환경 자동 복구

`doctor` 가 감지한 문제 중 **whitelisted repair action** 만 적용합니다. raw 데이터 삭제 / vault 수정 등 파괴적 작업은 절대 수행하지 않습니다.

## 실행

```bash
synapse-memory doctor --fix
```

복구 후에도 ✗ 가 남아 있으면 수동 안내로 fallback 합니다.
