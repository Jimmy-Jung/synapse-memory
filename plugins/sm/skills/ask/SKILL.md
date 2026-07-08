---
name: ask
description: Use when the user asks a natural-language question that should be answered from their Obsidian vault ontology (concepts, projects, logs and the typed relations between them). Synthesizes an answer with `[[slug]]` Entity citations.
---

# /sm:ask — vault 온톨로지 질의

사용자가 본인 vault에 저장된 개념·프로젝트·로그와 그 관계에서 무언가를 찾아달라고 하면 이 skill을 호출합니다.

## 실행

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory ask "<질의>" [--top-k N]
```

- `--top-k`: 선별할 Entity 개수

출력은 합성된 답변 + 출처(`[[slug]]` Entity 인용)를 포함합니다. AI provider가 vault Entity를 선별하고 typed relation을 근거로 답변합니다. 출처를 그대로 보존해서 사용자에게 전달하세요.

## 언제 쓰면 안 되는가

- 단순 "오늘 한 일 정리" → `daily` skill
- 특정 주제의 시간순 입장 변화 → `recall` skill
- 의사결정 추천 → `decide` skill
- 이력서 합성 → `resume` skill
