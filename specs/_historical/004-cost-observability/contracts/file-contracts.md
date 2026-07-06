# File Contracts: Cost Observability

## `~/.synapse/private/cost.jsonl`

- **Format**: UTF-8 JSON Lines, one JSON object per external provider call.
- **Permissions**:
  - parent directory: `0700`
  - file: `0600`
- **Write behavior**: append-only. Existing valid rows are never edited except during corrupt-tail recovery.
- **Privacy**: raw prompt, raw response, vault text, card body, stderr body, feedback reason, API key, OAuth token fields are forbidden.

## JSON Line Schema

```json
{
  "event_id": "20260512T100000123456Z-a1b2c3d4",
  "ts": "2026-05-12T10:00:00.123456Z",
  "command": "ask",
  "provider": "claude",
  "model": "sonnet",
  "status": "success",
  "input_tokens": 1000,
  "output_tokens": 300,
  "usd": 0.0021,
  "pricing_source": "estimated",
  "elapsed_s": 4.1234,
  "error_kind": null
}
```

## Corrupt Tail Recovery

If a line cannot be parsed or fails schema validation:

1. Keep all readable prefix lines in `cost.jsonl`.
2. Move unreadable tail content to `cost.jsonl.bak.<event_id>`.
3. Set backup file permission to `0600`.
4. Continue append or summary using the readable prefix.

The recovery must not silently discard unreadable bytes.

## Prohibited Fields

The following keys must not appear in a persisted cost event:

- `prompt`
- `response`
- `content`
- `body`
- `document`
- `stderr`
- `stdout`
- `reason`
- `token`
- `api_key`
- `oauth`
