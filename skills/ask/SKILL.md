---
name: ask
description: Use when the user asks a natural-language question that should be answered from their Obsidian vault / Card store via local RAG (e.g. "내 vault에서 X 찾아줘", "내가 작성한 X 자료 보여줘"). Synthesizes an answer with citations from Project/Company Cards and raw chunks.
---

# /sm:ask — vault RAG 질의

사용자가 본인 vault에 저장된 메모·Card·raw 노트에서 무언가를 찾아달라고 하면 이 skill을 호출합니다.

## 실행

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory ask "<질의>" [--hybrid] [--kind project|company] [--top-k N]
```

- `--hybrid`: dense + BM25 RRF 검색
- `--kind`: 특정 Card 종류로 제한
- `--top-k`: 검색 결과 개수

출력은 합성된 답변 + 출처(Card/raw chunk 이름) 인용을 포함합니다. 출처를 그대로 보존해서 사용자에게 전달하세요.

## 언제 쓰면 안 되는가

- 단순 "오늘 한 일 정리" → `daily` skill
- 특정 주제의 시간순 입장 변화 → `recall` skill
- 의사결정 추천 → `decide` skill
- 이력서 합성 → `resume` skill
