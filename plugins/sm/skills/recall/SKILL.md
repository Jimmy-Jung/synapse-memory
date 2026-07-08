---
name: recall
description: Use when the user wants to recall how their thinking on a topic evolved over time (e.g. "내가 X에 대해 뭐라 했었지?", "Y에 대한 내 입장 변화 보여줘", "Z 주제 회상해줘"). Returns chronological perspective shifts from their vault — second-brain mode, not generic Q&A.
---

# /sm:recall — 주제별 시간순 회상

사용자가 본인이 과거에 어떤 주제에 대해 적은 글을 시간순으로 회상하고 싶을 때 호출합니다. 단순 검색이 아니라 **입장 변화 분석** 까지 수행합니다.

## 실행

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory persona what-did-i-think "<주제>" [--timeline] [--by time|distance] [--limit N]
```

- `--timeline`: 날짜순으로 입장 변화 요약
- `--by`: 정렬 기준 (time / 의미 거리)
- `--limit`: 출력 카드 최대 수 (기본 20)

## ask와의 차이

- `ask`: "X가 뭐야?" / "X 찾아줘" — 단발 질의
- `recall`: "X에 대한 내 생각 변화" — 시간축 기반 자기 회상
