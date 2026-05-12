# Quickstart: Daily Resilience

이 quickstart 는 실제 사용자 vault 를 가능한 한 건드리지 않고 mocked/unit test 와 dry-run 중심으로 검증한다.

## 1. 환경 확인

```bash
synapse-memory doctor
```

기대: apfel/AI provider 상태와 무관하게 L0/vault 경로 진단이 표시된다.

## 2. dry-run 기본 stage 확인

```bash
synapse-memory daily --dry-run
```

기대: 모든 daily stage 가 순서대로 표시된다.

## 3. resume dry-run 확인

```bash
synapse-memory daily --dry-run --resume-from classify
```

기대: classify 이전 stage 는 resume skip 으로 표시되고 classify 이후 stage 는 실행 대상으로 표시된다.

## 4. invalid resume 확인

```bash
synapse-memory daily --resume-from nope
```

기대: exit 2, valid stage 목록 출력, 어떤 stage 도 실행되지 않음.

## 5. unit tests

```bash
python3 -m pytest tests/test_daily.py tests/test_daily_cli.py -q
```

기대: dependency skip, resume, report rendering, CLI exit code 테스트 통과.

## 6. DailyReport 확인

mocked run 또는 실제 run 후:

```bash
ls \"$(synapse-memory debug vault-path 2>/dev/null || echo '<vault>')\"/90_System/AI/DailyReports/
```

debug 명령이 없으면 vault 의 `90_System/AI/DailyReports/YYYY-MM-DD.md` 를 직접 확인한다.

## 7. CI workflow 확인

```bash
test -f .github/workflows/ci.yml
```

기대: pytest, ruff, mypy job 이 정의되어 있다.

## 8. 전체 gate

```bash
uvx ruff check src/synapse_memory/daily.py src/synapse_memory/cli.py tests/test_daily.py tests/test_daily_cli.py
python3 -m mypy --strict src/synapse_memory/daily.py
python3 -m pytest tests/ -W ignore::DeprecationWarning
```

기대: 모두 통과.
