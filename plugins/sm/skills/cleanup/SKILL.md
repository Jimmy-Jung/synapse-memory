---
name: cleanup
description: Use when the user wants to tidy their vault — "vault 정리해줘", "오래된 메모 archive", "휴면 Card 정리". Moves stale / empty / dormant items to an archive folder. NEVER permanently deletes anything.
---

# /sm:cleanup — vault 청소 도우미

오래된 / 휴면 / 빈 자료를 archive 폴더로 **이동** 합니다. 영구 삭제는 0건입니다.

## 실행

```bash
synapse-memory cleanup
```

(인자 없이 호출 후, CLI가 대화형으로 카테고리 — `inbox stale` / `dormant projects` / `empty cards` 등 — 를 묻습니다.)

임계값 (예: "60일 이상 미접근") 은 `config` skill 로 조정합니다.
