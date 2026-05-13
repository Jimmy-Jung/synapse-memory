# File Contracts — Feedback Loop

## F1. `~/.synapse/private/feedback.jsonl`

### Schema

```json
{
  "event_id": "20260512T032455123456Z-a1b2c3d4",
  "ts": "2026-05-12T03:24:55.123456Z",
  "target_kind": "card",
  "target_ref": "sample-ios-app",
  "action": "reject",
  "weight": -0.3,
  "reason": "관련 없음",
  "answer_id_context": "20260512T032400000000Z-f00dbabe"
}
```

### Policy

- Directory mode: `0700`; file mode: `0600`.
- Append-only. No in-place mutation.
- One JSON object per line, UTF-8, trailing newline required.
- If corruption is detected, move the first bad line through EOF to `feedback.jsonl.bak.<timestamp>` and keep readable prefix.

## F2. `~/.synapse/private/last_response.json`

### Schema

```json
{
  "answer_id": "20260512T032400000000Z-f00dbabe",
  "ts": "2026-05-12T03:24:00.000000Z",
  "command": "ask",
  "query": "클린 아키텍처에서 내가 한 생각",
  "session_id": null,
  "citations": [
    {
      "target_kind": "card",
      "target_ref": "sample-ios-app",
      "source_kind": "card_project",
      "display_name": "샘플 명상앱 iOS"
    }
  ]
}
```

### Policy

- Directory mode: `0700`; file mode: `0600`.
- Latest successful answer only.
- Do not store full answer text.
- If write fails, answer-producing endpoint should still return its answer and emit a warning through the existing CLI layer when possible.

## F3. Card Metadata

Card vector metadata gains:

```json
{
  "feedback_score": 0.85
}
```

### Policy

- Default score: `1.0`.
- Allowed range: `[0.5, 1.5]`.
- Score is derived from feedback events and can be recomputed.
- Card markdown content is not mutated by feedback application.
