# File Contracts: Daily Resilience

## `<vault>/90_System/AI/DailyReports/YYYY-MM-DD.md`

- **Format**: UTF-8 Markdown with YAML frontmatter.
- **Write behavior**: deterministic overwrite for the same date/run target. No duplicate daily report files for the same local date.
- **Privacy**: raw prompt, raw response, card body, note body, message body, OAuth token, API key fields are forbidden.

## Frontmatter

```yaml
---
date: 2026-05-12
total_elapsed_s: 12.3
errors_count: 1
skipped_count: 3
new_cards: 0
new_facts: 0
est_usd: 0.0129
resume_from: classify
---
```

## Body

```markdown
# Daily Report — 2026-05-12

## Stage Summary

| Stage | Status | Elapsed | Summary | Reason |
|---|---:|---:|---|---|
| collect_claude_code | success | 0.2s | mirrored=0 |  |
| classify | failed | 1.0s |  | AI provider 미설치 |
| generate | skipped | 0.0s |  | requires classify |

## Failures

- classify: AI provider 미설치

## Resume

Re-run from the failed stage:

```bash
synapse-memory daily --resume-from classify
```
```

## Cost Source

DailyReport may read `~/.synapse/private/cost.jsonl` through existing cost summary helpers. It must not copy raw prompt/response text because cost events do not contain those fields.
