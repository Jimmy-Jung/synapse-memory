---
name: onboard
description: Use for FIRST-TIME users — "synapse-memory 어떻게 써?", "처음인데 뭐부터?", "맛 좀 보여줘". Picks the ONE biggest pain among 5 onboarding paths and walks the user through it end-to-end. Not a generic tutorial.
---

# /sm:onboard — 최초 사용자 인도

5 가지 답답함 (recall / decide / resume / ask / daily) 중 사용자가 가장 크게 느끼는 **한 가지만** 끝까지 체험시키는 짧은 wedge.

## 실행

```bash
synapse-memory doctor
synapse-memory setup --dry-run
synapse-memory context render
synapse-memory daily --quick --dry-run
```

전용 `onboard` CLI는 없습니다. 이 skill이 사용자 답답함을 한 가지로 좁힌 뒤,
위의 실제 명령 중 필요한 read-only/dry-run 경로를 골라 시연합니다.

여러 기능을 동시에 설명하지 마세요. 첫 사용자는 ONE wedge.
