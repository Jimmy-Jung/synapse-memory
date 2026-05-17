# Implementation Plan: Private 폴더 + 외부 AI 차단 + /sm:redact

**Branch**: `0.10.0/feature/012-private-permissions` | **Date**: 2026-05-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-private-permissions/spec.md`

## Summary

기존 3-pass redaction 인프라(`redaction/__init__.py:redact_full`)를 그대로 재사용해 `synapse-memory redact file <path>` 서브커맨드를 신설한다. vault 차단은 `.claudeignore`가 아닌 `permissions.deny` 매커니즘(Spike 1 결과 반영)을 docs와 doctor 체크로 안내. Codex는 정책 기반(AGENTS.md) 가이드만. 모든 변경 TDD로 진행.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: 기존 — `redaction.pass1.redact`, `redaction.pass2.redact_full`, `llm.apfel` wrapper. 신규 의존성 0.
**Storage**: 로컬 파일시스템 read only (입력 파일). 출력: stdout 또는 `--out` 지정 경로.
**Testing**: pytest. apfel 의존 시나리오는 mock 또는 skip marker로 처리.
**Target Platform**: macOS / Linux CLI. apfel은 macOS 26+ Apple Silicon만 동작 → fallback 경로 필수.
**Project Type**: Python CLI library.
**Performance Goals**: 1 MB 미만 입력에 5초 이내 응답 (SC-001).
**Constraints**: 1 MB 입력 한도, UTF-8 텍스트만, apfel 미설치 시 Pass 1 only fallback + 경고.
**Scale/Scope**: CLI 서브커맨드 1개 + doctor 1개 체크 추가 + skill/marketplace command 1개 + docs 1개 섹션.

## Constitution Check

| 원칙 | 결과 | 근거 |
|---|---|---|
| I. Local-First & Privacy | ✅ Pass | 입력 파일 로컬, 출력 로컬. 외부 LLM 호출 없음 (apfel은 on-device). 원본 파일 변경 없음. |
| II. Two-Pass Redaction (NON-NEGOTIABLE) | ✅ Pass | 기존 `redact_full(text, env=apfel)` 그대로 호출. Pass 1+2 둘 다 traverse. apfel 미설치 시 silent skip 금지, stderr 경고 + Pass 1 only. |
| III. Test-First Discipline (NON-NEGOTIABLE) | ✅ Pass (계획) | Red → Green → Refactor. Acceptance scenarios를 pytest로 1:1 매핑. |
| IV. Conversation-Context-Aware Endpoints | ✅ N/A | endpoint 변경 없음. |
| V. Reproducible Daily Pipeline & Observability | ✅ Pass | daily 영향 없음 (수동 호출만). stderr 경고 + 종료 코드로 관측 가능. |
| VI. Installation Consent Scoping | ✅ Pass | redact file는 사용자 명시 호출. doctor 체크는 read-only. vault `.claude/settings.json` 변경은 사용자 수동. |

**Gate**: 모두 통과.

## Phase 0: Research (간략)

외부 라이브러리 결정 없음:
- `redact_full(text: str, env: ApfelEnv) -> RedactionResult` (기존 `redaction/__init__.py`)
- `pass1.redact(text: str) -> RedactionResult` (apfel 미설치 시 fallback)
- 파일 크기 체크: `Path.stat().st_size` (stdlib)
- UTF-8 디코드 실패 검출: `path.read_text(encoding="utf-8")` → `UnicodeDecodeError`
- apfel 가용성 체크: 기존 `llm.apfel.ensure_apfel_available()` 또는 동등 헬퍼

`research.md` 별도 파일 불필요.

## Phase 1: Design

### Affected modules (변경 파일)

| 파일 | 변경 유형 | 변경 내용 |
|---|---|---|
| `src/synapse_memory/cli.py` | 수정 | `redact` 파서에 `file` 서브커맨드 + handler `cmd_redact_file` |
| `src/synapse_memory/doctor.py` | 수정 | Private 폴더 존재 + `.claude/settings.json` deny 누락 체크 함수 추가 |
| `tests/test_cli_redact_file.py` | 신규 | `redact file` 통합 테스트 (5 시나리오) |
| `tests/test_doctor_private_check.py` | 신규 | doctor의 Private 폴더 체크 단위 테스트 (3 시나리오) |
| `docs/reference.md` | 수정 | "개인 메모를 안전하게 외부 AI에 전달하기" 섹션 추가 (Private 폴더 + deny + redact 흐름) |
| 신규 skill: `skills/redact/SKILL.md` | 신규 | `/sm:redact <path>` 슬래시 매핑 |
| 신규 marketplace command: `commands/redact.md` | 신규 | Claude Code 슬래시 등록 |

### CLI 인터페이스

```
$ synapse-memory redact file <path> [--out PATH]

Options:
  --out PATH    redacted 결과를 stdout 대신 이 경로에 저장.

Exit codes:
  0 — 정상 (apfel 적용 또는 Pass 1 only fallback 모두 0)
  2 — 입력 파일 없음 / 1MB 초과 / binary
```

### `cmd_redact_file` 의사코드

```
def cmd_redact_file(args):
    path = Path(args.path).expanduser().resolve()
    if not path.is_file():
        print(f"파일 없음: {path}", file=sys.stderr); return 2
    if path.stat().st_size > 1 * 1024 * 1024:
        print("입력 1 MB 초과 — 분할 처리 권장", file=sys.stderr); return 2
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print("UTF-8 텍스트 아님 — skip", file=sys.stderr); return 2

    env = ensure_apfel_available()  # 또는 None
    if env is None:
        print("apfel 미설치 — Pass 1 only fallback", file=sys.stderr)
        result = pass1.redact(text)
        redacted = result.redacted
    else:
        result = redact_full(text, env=env)
        redacted = result.redacted

    if args.out:
        Path(args.out).expanduser().write_text(redacted, encoding="utf-8")
    else:
        sys.stdout.write(redacted)
    return 0
```

### doctor Private 폴더 체크 (FR-009)

```
def check_private_folder_deny(vault: Path) -> CheckResult:
    private = vault / "90_System" / "Private"
    if not private.is_dir():
        return CheckResult.skip("Private 폴더 미존재")
    settings = vault / ".claude" / "settings.json"
    if not settings.is_file():
        return CheckResult.warn(
            "Private 폴더 있음, 그러나 vault/.claude/settings.json 없음.\n"
            "  안내: settings.json에 permissions.deny 추가 필요."
        )
    data = json.loads(settings.read_text())
    deny = data.get("permissions", {}).get("deny", [])
    required = {
        "Read(./90_System/Private/**)",
        "Glob(./90_System/Private/**)",
        "Write(./90_System/Private/**)",
    }
    missing = required - set(deny)
    if missing:
        return CheckResult.warn(f"deny 누락: {sorted(missing)}")
    return CheckResult.ok("Private 차단 정상")
```

### TDD 순서

1. **Red**: `tests/test_cli_redact_file.py` — `redact file` 5 시나리오 (정상, redactlist 마스킹, --out, 파일없음 exit 2, UTF-8 디코드 실패 exit 2)
2. **Green**: `cli.py`에 `cmd_redact_file` + 서브파서 등록
3. **Red**: `tests/test_doctor_private_check.py` — 3 시나리오 (Private 미존재 skip, settings.json 없음 warn, deny 누락 warn)
4. **Green**: `doctor.py`에 체크 함수 + 등록
5. (의존 환경) apfel 미설치 fallback 테스트 — monkeypatch로 `ensure_apfel_available()` 반환 None 시뮬레이션
6. docs/reference.md + skill/command 파일 작성
7. 회귀: 전체 pytest 통과

## Project Structure

```text
specs/012-private-permissions/
├── spec.md              # 완료
├── plan.md              # 이 파일
└── tasks.md             # /speckit-tasks 단계

src/synapse_memory/
├── cli.py                       # [수정] redact file 서브커맨드 + cmd_redact_file
└── doctor.py                    # [수정] check_private_folder_deny + 등록

tests/
├── test_cli_redact_file.py      # [신규] redact file 5 시나리오
└── test_doctor_private_check.py # [신규] doctor Private 체크 3 시나리오

docs/
└── reference.md                 # [수정] "Private 메모 안전 전달" 섹션 추가

skills/
└── redact/SKILL.md              # [신규] /sm:redact

commands/
└── redact.md                    # [신규] marketplace command
```

**Structure Decision**: 단일 Python 패키지. 기존 `redact` 서브파서 아래 `file` 액션 추가 (`backfill`과 동등 레벨). 신규 모듈 추가 없음 — redaction 진입점은 기존 그대로 재사용.

## Complexity Tracking

Constitution 위반 없음.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | | |
