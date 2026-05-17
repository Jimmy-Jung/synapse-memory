# Implementation Plan: /sm:setup + /sm:sync — cross-project Profile marker

**Branch**: `0.11.0/feature/013-sm-setup-sync` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-sm-setup-sync/spec.md`

## Summary

신규 패키지 `synapse_memory.projects`를 도입해 (1) `~/.synapse/projects.yaml` registry 관리, (2) marker block 삽입·교체·idempotent 로직, (3) Profile/Patterns 핵심 요약 추출을 3개 모듈로 분리한다. CLI는 `setup`, `sync` 서브커맨드 신설. auto-trigger 없음 (사용자 결정). TDD 진행.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: 기존 `PyYAML`(`yaml.safe_load/dump`), stdlib(`pathlib`, `hashlib`, `datetime`). 신규 의존성 0.
**Storage**: `~/.synapse/projects.yaml`(YAML), 각 프로젝트의 `AGENTS.md`/`CLAUDE.md`(text). 백업은 `~/.synapse/sync-backups/`.
**Testing**: pytest. 임시 디렉터리(tmp_path) + monkeypatch로 `~/.synapse` 위치 재정의.
**Target Platform**: macOS / Linux CLI.
**Project Type**: Python CLI library.
**Performance Goals**: setup 1초 이내, 5개 프로젝트 sync 1초 이내 (SC-001/SC-003).
**Constraints**: idempotent(byte-level), 파싱 실패 시 fail-closed, marker 사이만 교체 — 외부 라인 보존.
**Scale/Scope**: 신규 패키지 1개 (3 모듈) + CLI 서브커맨드 2개 + skill/command 2쌍 + docs 1개 섹션.

## Constitution Check

| 원칙 | 결과 | 근거 |
|---|---|---|
| I. Local-First & Privacy | ✅ Pass | 모든 파일 로컬. 외부 LLM 호출 없음. marker 내용은 사용자 자체 Profile/Patterns 요약 (이미 사용자 승인된 데이터). |
| II. Two-Pass Redaction | ✅ N/A | redaction 경계 새로 만들지 않음. Profile/Patterns는 이미 사용자가 vault에 승인 반영한 내용. |
| III. Test-First Discipline | ✅ Pass (계획) | Red→Green→Refactor. spec acceptance를 pytest로 1:1 매핑. |
| IV. Conversation-Context-Aware Endpoints | ✅ N/A | endpoint 변경 없음. |
| V. Reproducible Daily Pipeline & Observability | ✅ Pass | daily 영향 없음. sync는 명시 호출만, 종료 코드로 관측 가능. |
| VI. Installation Consent Scoping | ✅ Pass | setup은 cwd 명시 호출. sync는 등록된 프로젝트만 (사용자가 setup으로 등록한 것). 자동 트리거 없음. |

**Gate**: 모두 통과.

## Phase 0: Research

- YAML write: `yaml.safe_dump(data, sort_keys=False)` (기존 `synapse_memory.config`에서 PyYAML 사용 중)
- atomic write: `Path.write_text` + 임시 파일 → `rename` (`os.replace`)로 atomic (POSIX 보장)
- 프로젝트 hash: `hashlib.sha1(str(path).encode()).hexdigest()[:8]` (백업 파일명용, 충돌 거의 없음)
- vault 경로 source: 기존 `get_vault_path()` (`collectors/obsidian.py`)
- Profile/Patterns 핵심 요약: 단순 N개 라인 추출. `Profile.md`에서 `- ` bullet 라인의 상위 N개 (frontmatter `confidence` 기반 정렬은 v1에선 생략 — 단순 라인 순서)

## Phase 1: Design

### Affected modules (변경 파일)

| 파일 | 변경 유형 | 변경 내용 |
|---|---|---|
| `src/synapse_memory/projects/__init__.py` | 신규 | 패키지 초기화 + public re-export |
| `src/synapse_memory/projects/registry.py` | 신규 | `~/.synapse/projects.yaml` read/write dataclass `ProjectEntry`, `load_registry`, `save_registry`, `upsert_entry`, `mark_state` |
| `src/synapse_memory/projects/marker.py` | 신규 | marker 파싱·교체·idempotent. `MARKER_START`/`MARKER_END` 상수, `inject_or_replace(file, body)`, `extract_block(file)`, custom error for unclosed marker |
| `src/synapse_memory/projects/summary.py` | 신규 | Profile/Patterns에서 상위 N/M 라인 추출 → marker body markdown 생성 |
| `src/synapse_memory/cli.py` | 수정 | `setup` / `sync` 서브커맨드 + `cmd_setup` / `cmd_sync` |
| `tests/test_projects_marker.py` | 신규 | marker 삽입·교체·unclosed 검증 (6 시나리오) |
| `tests/test_projects_registry.py` | 신규 | registry CRUD + atomic write (4 시나리오) |
| `tests/test_projects_summary.py` | 신규 | Profile/Patterns 요약 추출 (3 시나리오) |
| `tests/test_cli_setup_sync.py` | 신규 | CLI 통합 (5 시나리오) |
| `docs/reference.md` | 수정 | "다른 프로젝트에서 sm 컨텍스트 활용" 섹션 추가 |
| `commands/setup.md`, `commands/sync.md` | 신규 | Claude Code 슬래시 |
| `skills/setup/SKILL.md`, `skills/sync/SKILL.md` | 신규 | Codex skill |

### Module 설계

**`projects/registry.py`** — dataclass + 함수:
```python
@dataclass
class ProjectEntry:
    path: Path
    target: str  # "agents" | "claude" | "both"
    registered_at: datetime.date
    last_sync: datetime.date | None
    state: str = "active"  # "active" | "stale"

def load_registry(registry_path: Path) -> list[ProjectEntry]: ...
def save_registry(entries: list[ProjectEntry], registry_path: Path) -> None: ...
def upsert_entry(entries: list[ProjectEntry], new: ProjectEntry) -> list[ProjectEntry]: ...
def mark_stale(entries: list[ProjectEntry], path: Path) -> list[ProjectEntry]: ...
```

**`projects/marker.py`** — 단순 파싱:
```python
MARKER_START = "<!-- SYNAPSE-MEMORY START -->"
MARKER_END = "<!-- SYNAPSE-MEMORY END -->"

class MarkerParseError(ValueError): ...

def inject_or_replace(file: Path, body: str) -> tuple[bool, str | None]:
    """파일을 marker로 감싼 body로 갱신. 신규 생성/append/교체 자동 분기.
    Returns: (changed, backup_of_old_body or None)
    """

def extract_block(file: Path) -> str | None:
    """marker 사이 본문 추출. 없으면 None. unclosed면 MarkerParseError."""
```

**`projects/summary.py`** — markdown 생성:
```python
def generate_marker_body(
    profile_path: Path,
    patterns_path: Path,
    *,
    fact_top_n: int = 5,
    pattern_top_m: int = 4,
) -> str:
    """Profile/Patterns를 읽어 marker 안에 들어갈 markdown body 생성."""
```

### CLI 인터페이스

```
$ synapse-memory setup [--target {agents,claude,both}] [--dry-run]
$ synapse-memory sync [--current]

Setup options:
  --target agents|claude|both  기본값: both
  --dry-run                    실제 파일 변경 없이 의도된 변경 출력

Sync options:
  --current                    cwd 프로젝트만 갱신 (기본: 등록 전체)

Exit codes:
  0  정상
  1  marker 파싱 실패 (unclosed)
  2  vault 경로 없음 / cwd가 registry에 없음 (sync --current 시)
```

### TDD 순서

1. **Red**: `tests/test_projects_marker.py` (6 시나리오) — 신규 inject, append, replace, unclosed error, dry-run, extract_block
2. **Green**: `projects/marker.py` 구현
3. **Red**: `tests/test_projects_registry.py` (4) — load empty, save+load roundtrip, upsert (insert/update), mark_stale
4. **Green**: `projects/registry.py` 구현
5. **Red**: `tests/test_projects_summary.py` (3) — basic generation, fact_top_n 제한, pattern_top_m 제한
6. **Green**: `projects/summary.py` 구현
7. **Red**: `tests/test_cli_setup_sync.py` (5) — setup --target both, setup idempotent, setup --dry-run, sync 전체, sync --current
8. **Green**: `cli.py` 서브커맨드 추가
9. docs + skill + command 작성
10. 전체 회귀

## Project Structure

```text
specs/013-sm-setup-sync/
├── spec.md              # 완료
├── plan.md              # 이 파일
└── tasks.md             # 다음

src/synapse_memory/
├── cli.py                       # [수정] setup, sync 서브커맨드 + 핸들러
└── projects/                    # [신규]
    ├── __init__.py
    ├── registry.py
    ├── marker.py
    └── summary.py

tests/
├── test_projects_marker.py      # [신규] 6 시나리오
├── test_projects_registry.py    # [신규] 4 시나리오
├── test_projects_summary.py     # [신규] 3 시나리오
└── test_cli_setup_sync.py       # [신규] 5 시나리오

docs/reference.md                # [수정] "다른 프로젝트에서 sm 컨텍스트 활용" 섹션
commands/
├── setup.md                     # [신규]
└── sync.md                      # [신규]
skills/
├── setup/SKILL.md               # [신규]
└── sync/SKILL.md                # [신규]
```

**Structure Decision**: 단일 Python 패키지. 신규 `projects/` 서브패키지로 registry / marker / summary 3개 관심사 분리 — 각각 독립 테스트 가능. CLI는 기존 `cli.py`에 서브커맨드 추가.

## Complexity Tracking

Constitution 위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | | |
