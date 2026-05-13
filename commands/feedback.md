---
description: 사용자 피드백 기록 — 마지막 답변 거절 / Card·Pattern 가중치 조정
argument-hint: last --reject <이유> | last --accept | card <id> --accept|--reject <이유>
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory feedback $ARGUMENTS`

직전 `ask` / `persona what-did-i-think` / `persona decide` 답변이나 특정 Card·DecisionPattern 에 피드백 신호를 남깁니다. 기록은 로컬 private feedback log 에 append-only 로 저장되고, 다음 인덱싱·검색에서 Card ranking 가중치로 반영됩니다.

예시:
- `last --reject "관련 없음"`
- `last --accept`
- `card dansim-ios --reject "SwiftUI 주제에는 부적합"`
- `pattern pattern-b330dfadf791 --weight -0.3`

피드백 명령은 batch endpoint 입니다. 외부 LLM 호출 없이 로컬에서만 기록합니다.
