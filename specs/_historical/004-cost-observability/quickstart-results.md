# Quickstart Results: Cost Observability

**Date**: 2026-05-12
**Temp root**: `/tmp/synapse-cost-smoke.BaqNG0`

## 1. doctor
```text
Synapse Memory 환경 진단
============================================
✓ apfel 설치: /opt/homebrew/bin/apfel
  버전: apfel v1.3.3
✓ Apple Silicon (arm64)
✓ macOS 26.3.1 (Tahoe+)
✓ L0 루트: /private/tmp/synapse-cost-smoke.BaqNG0/private (0700)
✓ Claude Code CLI: /Users/<user>/.local/bin/claude [2.1.139 (Claude Code)] (model=sonnet)
============================================
✓ 준비 완료
```

## 2. fixture cost events
```text
wrote 2 fixture events
```

## 3. tail event
```json
{
    "command": "daily.generate",
    "elapsed_s": 33.7,
    "error_kind": null,
    "event_id": "20260512T042031005164Z-7d01506d",
    "input_tokens": 4200,
    "model": "haiku",
    "output_tokens": 1800,
    "pricing_source": "estimated",
    "provider": "claude",
    "status": "success",
    "ts": "2026-05-12T04:20:31.005164Z",
    "usd": 0.0098
}
```

## 4. summary table
```text
Cost summary (last 30 days, by command)
GROUP                     CALLS    INPUT   OUTPUT        USD    ELAPSED
ask                           1     1200      540     0.0031      12.4s
daily.generate                1     4200     1800     0.0098      33.7s
TOTAL                         2     5400     2340     0.0129      46.1s
```

## 5. summary JSON
```json
{
    "by": "model",
    "days": 30,
    "generated_at": "2026-05-12T04:20:31.265518Z",
    "groups": [
        {
            "calls": 1,
            "elapsed_s": 33.7,
            "first_seen": "2026-05-12T04:20:31.005164Z",
            "group": "haiku",
            "input_tokens": 4200,
            "last_seen": "2026-05-12T04:20:31.005164Z",
            "output_tokens": 1800,
            "usd": 0.0098
        },
        {
            "calls": 1,
            "elapsed_s": 12.4,
            "first_seen": "2026-05-12T04:20:31.003664Z",
            "group": "sonnet",
            "input_tokens": 1200,
            "last_seen": "2026-05-12T04:20:31.003664Z",
            "output_tokens": 540,
            "usd": 0.0031
        }
    ],
    "total": {
        "calls": 2,
        "elapsed_s": 46.1,
        "first_seen": "2026-05-12T04:20:31.003664Z",
        "group": "TOTAL",
        "input_tokens": 5400,
        "last_seen": "2026-05-12T04:20:31.005164Z",
        "output_tokens": 2340,
        "usd": 0.0129
    }
}
```

## 6. no-data branch
```text
데이터 없음 — 아직 기록된 cost event 가 없습니다.
```

## 7. corrupt-tail recovery
```text
Cost summary (last 30 days, by command)
GROUP                     CALLS    INPUT   OUTPUT        USD    ELAPSED
ask                           1       10        5     0.0001       1.0s
TOTAL                         1       10        5     0.0001       1.0s
/tmp/synapse-cost-smoke.BaqNG0/private/cost.jsonl.bak.20260512T042031527891Z-bf15e851
```
