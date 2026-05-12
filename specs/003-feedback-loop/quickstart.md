# Quickstart — Feedback Loop

## 전제

- `synapse-memory doctor` 가 green.
- vault 에 ProjectCard 또는 CompanyCard 가 1개 이상 있다.
- `ask` 또는 `me what-did-i-think` 가 정상 답변을 생성할 수 있다.

## 1. 직전 답변 생성

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory ask "클린 아키텍처에서 내가 반복해서 말한 기준은?"
```

기대:

```text
... 답변 본문 ...

Sources:
- dansim-ios
```

검증:

```bash
test -f ~/.synapse/private/last_response.json
python3 -m json.tool ~/.synapse/private/last_response.json
```

## 2. 직전 답변 거절 피드백

```bash
synapse-memory feedback last --reject "관련 없음 — 클린 아키텍처가 아니라 SwiftUI 이야기였음"
```

기대:

```text
✓ Recorded reject for last answer <answer_id> (targets=1, weight=-0.30)
  → next index will apply updated feedback_score
```

검증:

```bash
tail -1 ~/.synapse/private/feedback.jsonl | python3 -m json.tool
```

## 3. 특정 카드 accept

```bash
synapse-memory feedback card dansim-ios --accept
```

기대:

```text
✓ Recorded accept for card dansim-ios (weight=+0.20)
  → next index will apply updated feedback_score
```

## 4. 다음 인덱싱 반영

```bash
synapse-memory rag index
```

기대:

```text
indexed project=<n> company=<n> feedback_scores=<m>
```

검증:

```bash
synapse-memory rag search "클린 아키텍처" --top-k 5
```

결과 metadata 또는 debug 출력에서 피드백 대상 card 의 `feedback_score` 가 기본값 `1.0` 과 달라졌는지 확인한다.

## 5. no-op 검증

```bash
rm -f ~/.synapse/private/last_response.json
synapse-memory feedback last --reject "대상 없음"
```

기대:

```text
No recent answer found. Run ask/me first, then retry feedback last.
```

검증:

```bash
test ! -f ~/.synapse/private/feedback.jsonl || tail -1 ~/.synapse/private/feedback.jsonl
```

마지막 줄이 새 no-op 이벤트가 아니어야 한다.
