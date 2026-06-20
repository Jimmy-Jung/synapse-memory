---
name: decide
description: Use when the user faces a decision and wants a recommendation grounded in their own past patterns (e.g. "Z 상황에서 어떻게 결정하지?", "이거 받을까 말까?", "A vs B 골라줘"). Acts as the user's clone — pulls from Profile.md + DecisionPatterns.md in the vault.
---

# /sm:decide — 의사결정 코파일럿 (내 클론 모드)

사용자가 어떤 결정을 내려야 할 때, **본인의 과거 결정 패턴 + 가치관 + 기술 선호** 를 반영한 추천을 제공합니다.

## 실행

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory decide "<상황 설명>"
```

내부적으로 vault 의 `Profile.md` + `DecisionPatterns.md` + 관련 Card 를 RAG 로 retrieve 한 뒤 합성합니다. 결과는 추천 + 근거 패턴 + 출처 Card 인용.

## ask / recall 과의 차이

- `ask`: 사실 질의 답변
- `recall`: 시간순 입장 변화
- `decide`: "당신이라면 어떻게 할지" 추천 — 답을 강요 받는 모드
