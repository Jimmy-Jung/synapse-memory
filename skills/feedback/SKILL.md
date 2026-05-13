---
name: feedback
description: Use when the user rejects or accepts the last assistant answer with reasoning ("이 답변 별로야", "이 Card 틀렸어 빼줘", "방금 거 맞아 학습해"). Adjusts Card / Pattern weights for future retrieval.
---

# /sm:feedback — 답변·Card 가중치 조정

직전 응답이나 특정 Card 에 대한 사용자 평가를 기록해서 retrieval / ranking 에 반영합니다. raw 사용자 데이터는 ~/.synapse/private/feedback.jsonl 에 0600 으로 저장됩니다.

## 실행

```bash
synapse-memory feedback last --reject "<이유>"
synapse-memory feedback last --accept
synapse-memory feedback card <id> --reject "<이유>"
```

피드백은 누적 가중치로만 사용되고 Card 본문을 즉시 수정하지 않습니다.
