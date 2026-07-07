# Implementation Plan: MemoryInbox / DailyReports 년·월 폴더 구조

**Branch**: `0.9.0/feature/011-yearmonth-folders` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-yearmonth-folders/spec.md`

## Summary

`save_profile_update`와 `write_daily_report`의 path 산출 부분에 `{YYYY}/{MM:02d}` 하위 디렉터리 1단계를 추가하고, 기존 flat 파일을 이동시키는 1회성 `migrate-folders` CLI 서브커맨드를 신설한다. 모든 변경은 idempotent하게 설계하고 TDD로 진행한다.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: 기존 — pathlib(stdlib), datetime(stdlib), PyYAML, click(없으면 argparse). 신규 의존성 없음.
**Storage**: 로컬 파일시스템 (vault markdown 파일들). 데이터베이스 변경 없음.
**Testing**: pytest (기존 ≥459 tests). 신규 unit + integration 테스트 추가.
**Target Platform**: macOS / Linux CLI (vault 파일시스템 접근만 필요).
**Project Type**: Python CLI library (`src/synapse_memory/`).
**Performance Goals**: migrate-folders는 vault당 수십~수백 파일 1회 처리. 5초 이내 완료 목표.
**Constraints**: idempotent, dry-run 지원, 충돌 시 fail-closed (덮어쓰기 금지), iCloud sync 환경 호환.
**Scale/Scope**: 영향 범위 — daily 파이프라인 2개 함수 수정 + 신규 CLI 서브커맨드 1개 + 신규 module 1개.

## Constitution Check

| 원칙 | 결과 | 근거 |
|---|---|---|
| I. Local-First & Privacy | ✅ Pass | 모든 파일은 vault 내부 로컬에 머무름. 외부 LLM 호출·전송 없음. |
| II. Two-Pass Redaction | ✅ N/A | 새 trust boundary 없음 (파일 위치만 변경). |
| III. Test-First Discipline | ✅ Pass (계획) | Red→Green→Refactor. spec의 acceptance scenarios를 pytest로 1:1 매핑. |
| IV. Conversation-Context-Aware Endpoints | ✅ N/A | endpoint 변경 없음. |
| V. Reproducible Daily Pipeline & Observability | ✅ Pass | daily는 그대로 idempotent. migrate-folders도 idempotent + dry-run + 충돌 보고. |
| VI. Installation Consent Scoping | ✅ Pass | migrate-folders는 명시 호출 (자동 실행 X). dry-run로 사전 확인. |

**Gate**: 모두 통과. Phase 0 research 단계 진입 가능.

## Phase 0: Research (간략)

이 feature는 외부 라이브러리·기술 선택 결정 없음. 모든 결정은 spec 단계에서 끝남:
- 디렉터리 생성 — `Path.mkdir(parents=True, exist_ok=True)` (stdlib).
- 파일 이동 — `Path.rename` 또는 `shutil.move`. iCloud 환경 안전성 위해 `shutil.move` 채택 (다른 device로 이동 시도 시 copy+delete fallback).
- 정규식 매치 — `^Profile-(\d{4})-(\d{2})-(\d{2})\.md$` / `^(\d{4})-(\d{2})-(\d{2})\.md$`.
- ISO 날짜 파싱 — `datetime.date.fromisoformat`.

`research.md` 별도 파일 불필요. 결정 사항은 본 plan에 인라인.

## Phase 1: Design

### Affected modules (변경 파일)

| 파일 | 변경 유형 | 변경 내용 |
|---|---|---|
| `src/synapse_memory/profile/extract.py` | 수정 | `save_profile_update` 함수의 path 산출 부분 변경 |
| `src/synapse_memory/daily.py` | 수정 | `write_daily_report` 함수의 path 산출 부분 변경 |
| `src/synapse_memory/folders/__init__.py` | 신규 | 공통 path helper (`year_month_path`) |
| `src/synapse_memory/folders/migrate.py` | 신규 | flat → year/month migration 핵심 로직 + 충돌 감지 |
| `src/synapse_memory/cli.py` | 수정 | `migrate-folders` 서브커맨드 추가 |
| `tests/test_folders_path.py` | 신규 | path helper 단위 테스트 |
| `tests/test_folders_migrate.py` | 신규 | migration 로직 단위 테스트 |
| `tests/test_daily_year_month.py` | 신규 | daily 실행 후 파일 경로 검증 |

### Module 설계

**`folders/__init__.py`** — 단일 helper 함수:
```python
def year_month_path(base: Path, date: datetime.date) -> Path:
    """`base/{YYYY}/{MM:02d}` 경로 반환. 디렉터리 생성은 호출자 책임."""
    return base / f"{date.year:04d}" / f"{date.month:02d}"
```

**`folders/migrate.py`** — 데이터클래스 + 함수:
```python
@dataclass(frozen=True)
class MigrationPlan:
    src: Path
    dst: Path
    date: datetime.date

@dataclass(frozen=True)
class MigrationResult:
    moved: list[MigrationPlan]
    skipped_unknown: list[Path]
    conflicts: list[tuple[Path, Path]]  # (src, dst-existing)
    errors: list[tuple[Path, str]]

def scan_flat_files(folder: Path, pattern: re.Pattern) -> list[MigrationPlan]: ...
def execute_migration(plans: list[MigrationPlan], *, dry_run: bool = False) -> MigrationResult: ...
```

핵심 함수 2개로 분리: scan(부작용 없음) + execute(부작용 있음). dry-run은 execute에 플래그.

### CLI 인터페이스

```
$ synapse-memory migrate-folders [--dry-run] [--report-unknown] [--vault PATH]

Options:
  --dry-run          Print intended moves without actually moving files.
  --report-unknown   List files skipped because their name didn't match the date pattern.
  --vault PATH       Override vault path (default: from config).
```

종료 코드:
- `0` — 정상 완료 (이동된 파일 수와 무관)
- `1` — 충돌 발생 (자동 해결 안 함, 사용자 결정 필요)
- `2` — 시스템 에러 (vault 경로 없음, 권한 부족 등)

### 경로 산출 부분 변경 (기능 본체)

`src/synapse_memory/profile/extract.py` 기존:
```python
inbox = vault / get_config().vault_folders.system.ai.memory_inbox
inbox.mkdir(parents=True, exist_ok=True)
today = datetime.date.today().isoformat()
path = inbox / f"Profile-{today}.md"
```

변경 후:
```python
from synapse_memory.folders import year_month_path

inbox_base = vault / get_config().vault_folders.system.ai.memory_inbox
today = datetime.date.today()
inbox = year_month_path(inbox_base, today)
inbox.mkdir(parents=True, exist_ok=True)
path = inbox / f"Profile-{today.isoformat()}.md"
```

`src/synapse_memory/daily.py` `write_daily_report`도 동일 패턴 적용.

### FR-011 대응 (후속 feature의 recursive 스캔)

이번 feature에서는 path 생성만 한다. apply-profile 등 후속 기능이 MemoryInbox를 읽을 때는 `glob("**/Profile-*.md")` 재귀 패턴을 써야 한다. 본 feature에서는 path helper에 인접한 `find_candidate_files(base: Path) -> list[Path]` 유틸을 함께 제공해 후속 feature가 한 줄로 재귀 스캔할 수 있게 한다.

### TDD 순서 (Red → Green)

1. **Red**: `tests/unit/test_folders_path.py` 작성 — `year_month_path()`가 올바른 경로 반환하는지 (date 입력별 5케이스)
2. **Green**: `folders/__init__.py` 구현
3. **Red**: `tests/integration/test_daily_year_month.py` — daily 실행 후 파일이 year/month에 생기는지 (tmp vault 사용)
4. **Green**: extract.py, daily.py 수정
5. **Red**: `tests/unit/test_folders_migrate.py` — scan/execute 단위 테스트 (5개 시나리오: 정상, 충돌, unknown, dry-run, idempotent)
6. **Green**: `folders/migrate.py` 구현
7. **Red**: CLI 호출 contract 테스트 — `synapse-memory migrate-folders --dry-run`이 종료 코드 0, 0 mutations
8. **Green**: cli.py에 서브커맨드 추가

## Project Structure

### Documentation (this feature)

```text
specs/011-yearmonth-folders/
├── plan.md              # 이 파일
├── spec.md              # 완성됨
└── tasks.md             # /speckit-tasks 단계에서 생성
```

(research.md, data-model.md, quickstart.md, contracts/ 폴더는 본 feature 단순성으로 생략. CLI contract는 plan에 인라인.)

### Source Code (repository root)

```text
src/synapse_memory/
├── cli.py                       # [수정] migrate-folders 서브커맨드 추가
├── daily.py                     # [수정] write_daily_report path 산출 변경
├── profile/
│   └── extract.py               # [수정] save_profile_update path 산출 변경
└── folders/                     # [신규] path helper + migration
    ├── __init__.py              # year_month_path, find_candidate_files
    └── migrate.py               # MigrationPlan, scan_flat_files, execute_migration

tests/                           # 기존 컨벤션: 평탄 구조 (subdir 없음)
├── test_folders_path.py         # [신규] path helper 단위 테스트
├── test_folders_migrate.py      # [신규] migration 단위 테스트
├── test_daily_year_month.py     # [신규] daily 실행 → 파일 위치 검증
└── test_cli_migrate_folders.py  # [신규] migrate-folders CLI 통합 테스트
```

**Structure Decision**: 단일 Python 패키지 (Option 1). 신규 `folders/` 서브 패키지는 daily/profile 양쪽이 공유하는 공통 path 로직을 격리하고, migration 로직과 함께 묶기 위함. CLI는 기존 `cli.py`에 서브커맨드 추가만.

## Complexity Tracking

> Constitution Check 위반 없음. 이 섹션 비워둠.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | | |
