---
description: 특정 주제에 대한 회상 (세컨드 브레인 모드 — 입장 변화 분석)
argument-hint: <주제> [--hybrid] [--timeline] [--by time|distance] [--limit N]
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory persona what-did-i-think $ARGUMENTS`

기본은 cosine distance 기반 AI provider 통합 답변이며, `--hybrid` 옵션을 붙이면 dense + BM25 RRF 검색 후 답변합니다. `--timeline` 또는 `--by time` 옵션을 붙이면 vault Card 를 period_end 내림차순으로 분기·월 그룹화한 시간순 회상이 됩니다 (외부 LLM 호출 없이 로컬에서 생성).

옵션:
- `--timeline` 시간순 분기 그룹 (권장 — 회상 본연의 경험)
- `--by time` `--timeline` 별칭
- `--by distance` 기존 cosine + Claude 통합 답변 (기본)
- `--hybrid` distance 모드에서 dense + BM25 RRF 검색
- `--limit N` 출력 카드 최대 수 (기본 20, 범위 1~100)

위 출력은 사용자가 해당 주제에 대해 vault 안에서 시간순으로 어떤 생각을 거쳐왔는지 정리한 회상 결과입니다. 입장 변화 / 의사결정 분기점을 강조하여 사용자에게 전달하세요.
