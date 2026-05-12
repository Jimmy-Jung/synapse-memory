# Redaction Eval Results: Raw RAG Hybrid

**Date**: 2026-05-12  
**Command**: `python3 -m synapse_memory.cli eval golden --set tests/golden/pii_synthetic.json`  
**Golden set**: `tests/golden/pii_synthetic.json`  
**Samples**: 58  
**Elapsed**: 70.4s

## Summary

| Metric | Value |
|---|---:|
| TP | 47 |
| FP | 0 |
| FN | 1 |
| Precision | 1.00 |
| Recall | 0.98 |
| Overall F1 | 0.99 |
| Perfect samples | 57/58 (98.3%) |

## Category Notes

| Category | F1 |
|---|---:|
| person_name | 0.96 |
| all other reported categories | 1.00 |

## Failure

- `person-005` — FN `person_name: Mike`

## Gate

Pass. Constitution thresholds remain satisfied:

- Pass 1 target F1 >= 0.95: no deterministic category regression observed in this run.
- Pass 2 target F1 >= 0.80: contextual categories remain above threshold; `person_name` F1 = 0.96.
