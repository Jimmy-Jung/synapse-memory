---
description: 자연어 질의 → 온톨로지 Entity 선별 → Claude 합성 답변 (출처 인용)
argument-hint: <질의> [--top-k N]
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory ask "$ARGUMENTS"`

위 출력은 synapse-memory CLI가 vault의 온톨로지 Entity(개념·프로젝트·로그 등)를 AI provider로 선별하고, 그 사이의 typed relation을 근거로 합성한 답변입니다. 결과를 사용자에게 그대로 전달하세요. 출처(`[[slug]]` Entity 인용)가 포함되어 있으므로 그대로 보존합니다.
