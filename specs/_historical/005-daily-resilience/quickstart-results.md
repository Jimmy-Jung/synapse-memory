# Quickstart Results: Daily Resilience

**Date**: 2026-05-12

## 1. dry-run 기본 stage 확인

```text
$ python3 -m synapse_memory.cli daily --dry-run
[DRY RUN] 실행 단계:
  [x] collect_claude_code
  [x] collect_obsidian
  [x] classify
  [x] generate
  [x] index
  [x] update_profile
  [x] report
```

## 2. resume dry-run 확인

```text
$ python3 -m synapse_memory.cli daily --dry-run --resume-from classify
[DRY RUN] 실행 단계:
  [ ] collect_claude_code (resume skip)
  [ ] collect_obsidian (resume skip)
  [x] classify
  [x] generate
  [x] index
  [x] update_profile
  [x] report
```

## 3. invalid resume 확인

```text
$ python3 -m synapse_memory.cli daily --resume-from nope
usage: synapse-memory daily [-h] [--only ONLY] [--skip SKIP]
                            [--resume-from {collect_claude_code,collect_obsidian,classify,generate,index,update_profile,report}]
                            [--classify-model CLASSIFY_MODEL]
                            [--generate-model GENERATE_MODEL]
                            [--profile-model PROFILE_MODEL]
                            [--profile-sample-lines PROFILE_SAMPLE_LINES]
                            [--profile-facts-only] [--dry-run]
synapse-memory daily: error: argument --resume-from: invalid choice: 'nope' (choose from collect_claude_code, collect_obsidian, classify, generate, index, update_profile, report)
```

Exit code: `2`

## 4. unit tests

```text
$ python3 -m pytest tests/test_daily.py tests/test_daily_cli.py -q
.................                                                        [100%]
17 passed
```

## 5. CI workflow 확인

```text
$ test -f .github/workflows/ci.yml
pass
```

Workflow contains pytest, ruff, and mypy gates without private credentials.
