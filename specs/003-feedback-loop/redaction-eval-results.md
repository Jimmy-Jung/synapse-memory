# Redaction Eval Results — 003 Feedback Loop

**Date**: 2026-05-12  
**Command**: `synapse-memory eval golden --show-failures 0`  
**Golden set**: `tests/golden/pii_synthetic.json` (58 samples)

## Overall

```text
OVERALL                  47    0    1   1.00   0.98   0.99
완벽한 sample: 57/58 (98.3%)
```

## Pass Split

```text
Pass1 deterministic: TP=29 FP=0 FN=0 P=1.0000 R=1.0000 F1=1.0000
Pass2 contextual: TP=18 FP=0 FN=1 P=1.0000 R=0.9474 F1=0.9730
```

## Gate

- Pass1 F1 >= 0.95: pass
- Pass2 F1 >= 0.80: pass

## Note

`003-feedback-loop` was branched from `main`, where the pre-existing Pass2 golden gate regression was still present. Commit `2df2a43` cherry-picks `fix(redaction): Pass2 golden gate 회복` into this branch before recording the passing eval above.
