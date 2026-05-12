---
description: 자연어 질의 → RAG retrieve → Claude 합성 답변 (출처 인용)
argument-hint: <질의> [--hybrid] [--kind project|company] [--top-k N]
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory ask "$ARGUMENTS"`

위 출력은 synapse-memory CLI가 vault RAG 검색 + AI provider로 합성한 답변입니다. `--hybrid`가 포함되면 dense + BM25 RRF 검색 결과입니다. 결과를 사용자에게 그대로 전달하세요. 출처(Card/raw chunk 이름)가 포함되어 있으므로 그대로 보존합니다.
