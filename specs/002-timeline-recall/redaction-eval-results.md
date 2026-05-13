# Redaction Golden Eval Results

Author: Synapse Memory Maintainers
Date: 2026-05-12
Branch: `002-timeline-recall`
Commit: `2e8d431`

## Summary

Command:

```bash
synapse-memory eval golden --show-failures 0
```

Result: **FAIL for merge gate**.

| Gate | Threshold | Observed | Status |
|---|---:|---:|---|
| Pass1 deterministic F1 | >= 0.95 | 1.0000 | PASS |
| Pass2/contextual F1 | >= 0.80 | 0.7619 | FAIL |
| Full `redact_full` overall F1 | reference | 0.90 | INFO |

The timeline recall feature did not modify redaction code, but the current golden eval does not satisfy the parent merge gate because Pass2/contextual aggregate F1 is below 0.80.

## Full Eval Output

```text
$ synapse-memory eval golden --show-failures 0
평가: 58 samples ← pii_synthetic.json
.....25.....50.  (68.0s)

카테고리                     TP   FP   FN      P      R     F1
------------------------------------------------------------
address                   1    1    1   0.50   0.50   0.50
api_key_github            1    0    0   1.00   1.00   1.00
api_key_sk                1    0    0   1.00   1.00   1.00
aws_key                   1    0    0   1.00   1.00   1.00
bearer                    1    0    0   1.00   1.00   1.00
card                      4    0    0   1.00   1.00   1.00
email                     8    0    0   1.00   1.00   1.00
ipv4                      3    0    0   1.00   1.00   1.00
jwt                       1    0    0   1.00   1.00   1.00
org_name                  2    0    1   1.00   0.67   0.80
person_name              11    5    1   0.69   0.92   0.79
phone_kr                  7    0    0   1.00   1.00   1.00
rrn                       2    0    0   1.00   1.00   1.00
secret                    2    0    0   1.00   1.00   1.00
sensitive_topic           0    1    0   0.00   0.00   0.00
------------------------------------------------------------
OVERALL                  45    7    3   0.87   0.94   0.90

완벽한 sample: 49/58 (84.5%)
```

## Pass Split Calculation

Pass1 deterministic categories:

```text
jwt, aws_key, api_key_sk, api_key_github, bearer, email, rrn, card, phone_kr, ipv4
```

```text
Pass1 deterministic categories: TP=29 FP=0 FN=0 P=1.0000 R=1.0000 F1=1.0000
```

Pass2/contextual categories:

```text
address, org_name, person_name, secret, sensitive_topic
```

```text
Pass2/contextual categories from full eval: TP=16 FP=7 FN=3 P=0.6957 R=0.8421 F1=0.7619
```

## Merge-Gate Implication

Parent plan requires:

- Pass1 F1 >= 0.95
- Pass2 F1 >= 0.80

Current result:

- Pass1 passes.
- Pass2 fails by 0.0381 F1.

This should remain a blocking item unless the team explicitly scopes this PR to timeline-only and accepts the pre-existing redaction gate failure separately.
