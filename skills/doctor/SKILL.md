---
name: doctor
description: Use when the user reports installation issues, asks "환경 정상인지 봐줘", "synapse-memory 동작 확인", or before first run. Checks Apple Silicon, macOS version, vault path, apfel, Claude Code CLI availability, Python version, and config sanity.
---

# /sm:doctor — 환경 진단

Synapse Memory 가 의존하는 외부 도구 / 경로 / 런타임을 점검합니다.

## 실행

```bash
synapse-memory doctor
```

✗ 항목이 있으면 해결 방법을 안내하고, 자동 복구 가능하면 `fix` skill (`synapse-memory doctor --fix`) 을 제안하세요. 모두 ✓이면 다음 단계 (`daily` 또는 `ask`) 를 안내합니다.

## 언제 안 쓰는가

- 자동 복구까지 한 번에 → `fix` skill
- 비용 점검 → `cost` skill
