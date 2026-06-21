---
name: assistant
description: Use when the user says "오늘 뭐하면 좋을까", "synapse-memory 비서 모드", "추천 작업 알려줘", or wants proactive task suggestions. Recommends 1–3 actions from existing data, executes on user approval.
---

# /sm:assistant — 일상 비서 모드

vault / Card / 최근 활동을 종합해서 **오늘 추천 작업 1~3 개** 를 제안하고, 사용자가 동의하면 그 작업을 대신 실행합니다. (예: "오늘 X Card 갱신할까?" → 승인 시 daily 또는 resume 등 다른 skill 호출).

## 실행

```bash
synapse-memory assistant-status
synapse-memory assistant-status --json
```

`assistant-status`는 read-only 진단과 추천만 출력합니다. 사용자가 번호 또는 자연어로
승인하면 추천에 적힌 실제 명령(`daily`, `cleanup scan`, `persona draft-resume` 등)을
별도로 실행하세요.
