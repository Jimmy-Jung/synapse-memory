# CLI Contracts: Daily Resilience

## `synapse-memory daily [options]`

- **분류**: batch
- **기존 옵션 유지**:
  - `--only a,b`
  - `--skip a,b`
  - `--classify-model`
  - `--generate-model`
  - `--profile-model`
  - `--profile-sample-lines`
  - `--profile-facts-only`
  - `--dry-run`
- **신규 옵션**:
  - `--resume-from <stage>`: 지정 stage 이전은 실행하지 않고 resume skip 으로 기록한다.

## Stage Names

Stable stage id:

```text
collect_claude_code
collect_obsidian
classify
generate
index
update_profile
report
```

`report` 는 DailyReport 작성 stage 이며 사용자가 `--skip report` 할 수 있다.

## Exit Codes

- `0`: 선택된 executable stage 가 모두 성공.
- `1`: stage 실패가 하나 이상 있음. downstream skip 은 실패 원인 stage 를 보존한다.
- `2`: invalid CLI input. 예: unknown `--resume-from` stage.

## Stdout Summary

```text
============================================================
Daily 총 시간: 12.3s
실행 단계: 7, 실패: 1, 건너뜀: 3
  ✓ collect_claude_code       0.2s  mirrored=0
  ✓ collect_obsidian          0.3s  mirrored=1
  ✗ classify                  1.0s  AI provider 미설치
  - generate                  0.0s  skipped: requires classify
  - index                     0.0s  skipped: requires generate
  - update_profile            0.0s  skipped: requires collect_claude_code
  ✓ report                    0.1s  DailyReports/2026-05-12.md
```

## Invalid Resume

Command:

```bash
synapse-memory daily --resume-from nope
```

stderr:

```text
✗ unknown daily stage: nope
valid stages: collect_claude_code, collect_obsidian, classify, generate, index, update_profile, report
```

exit: `2`

## Dry Run

`--dry-run --resume-from classify` prints selected/resume-skipped stages but executes nothing.

```text
[DRY RUN] 실행 단계:
  [ ] collect_claude_code (resume skip)
  [ ] collect_obsidian (resume skip)
  [x] classify
  [x] generate
  [x] index
  [x] update_profile
  [x] report
```
