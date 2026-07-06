# Redaction Eval Results: Daily Resilience

**Date**: 2026-05-12  
**Command**: `python3 -m synapse_memory.cli eval golden --show-failures 0`  
**Golden set**: `tests/golden/pii_synthetic.json` (58 samples)

## Overall

```text
OVERALL                  47    0    1   1.00   0.98   0.99
완벽한 sample: 57/58 (98.3%)
elapsed: 70.9s
```

## Pass Split

Category split follows the project convention:

- Pass 1 deterministic: categories outside `person_name`, `org_name`, `address`, `sensitive_topic`, `secret`
- Pass 2 contextual: `person_name`, `org_name`, `address`, `sensitive_topic`, `secret`

```text
Pass1 deterministic: TP=29 FP=0 FN=0 P=1.0000 R=1.0000 F1=1.0000
Pass2 contextual:    TP=18 FP=0 FN=1 P=1.0000 R=0.9474 F1=0.9730
```

## Gate

- Pass1 F1 >= 0.95: PASS
- Pass2 F1 >= 0.80: PASS
- No redaction regression observed for this feature.
