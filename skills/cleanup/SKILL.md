---
name: cleanup
description: Use when the user wants to tidy their vault — "vault 정리해줘", "오래된 메모 archive", "휴면 Card 정리". Moves stale / empty / dormant items to an archive folder. NEVER permanently deletes anything.
---

# /sm:cleanup — vault 청소 도우미

오래된 / 휴면 / 빈 자료를 archive 폴더로 **이동** 합니다. 영구 삭제는 0건입니다.

## 실행

```bash
synapse-memory cleanup scan
synapse-memory cleanup scan --json
synapse-memory cleanup apply --dry-run
synapse-memory cleanup apply --apply
```

먼저 `cleanup scan`으로 후보를 보여줍니다. 사용자가 승인하기 전에는
`cleanup apply --apply`를 실행하지 마세요. `cleanup apply`와 `cleanup apply --dry-run`은
둘 다 dry-run입니다.

임계값 (예: "60일 이상 미접근") 은 `config` skill 로 조정합니다.
