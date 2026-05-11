---
description: 자연어 질의 → RAG retrieve → Claude 합성 답변 (출처 인용)
argument-hint: <질의>
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory ask "$ARGUMENTS"`

위 출력은 synapse-memory CLI가 vault RAG 검색 + Claude API로 합성한 답변입니다. 결과를 사용자에게 그대로 전달하세요. 출처(Card 이름)가 포함되어 있으므로 그대로 보존합니다.
