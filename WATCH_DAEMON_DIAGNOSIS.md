# Watch 데몬 갱신 중단 — 진단 및 개선 방향

**작성일:** 2026-06-19
**작성자:** JunyoungJung
**대상:** Codex 인계 (수정 작업)
**상태:** 근본 원인 재확인, 필수 코드 수정 적용됨 (기존 LaunchAgent 재설치 필요)

---

## 1. 증상

로컬 watch 데몬(`com.synapse-memory.watch`)이 claude/codex 세션을 읽어 Obsidian vault를
주기적으로 갱신해야 하는데, **아무 갱신도 발생하지 않음**.

- `/sm:doctor` → 전 항목 ✓ (설치/config만 검사, 실제 처리 결과는 미검사)
- watch 출력 로그: 매 사이클 `watch run: docs=25, pages=0` 반복 — doc 25개를 보지만 페이지 0개 생성
- watermark `claude-code` = `2026-06-12T09:17:58` 에 고정 (오늘 06-19, **7일째 정지**)

---

## 2. 근본 원인 (확정)

**데몬은 정상 실행 중이나, launchd 환경에서 `claude` CLI를 찾지 못해 매 doc 처리가 전부 실패한다.**

### 원인 사슬

| 단계 | 위치 | 사실 |
|---|---|---|
| 1 | `src/synapse_memory/wiki/launchd.py:26-40` (`build_plist`, 수정 전) | plist payload에 `EnvironmentVariables` 키 없음 → 데몬은 launchd 기본 PATH로 실행 |
| 2 | (런타임) | `launchctl getenv PATH` = **빈 값**. launchd 기본 PATH(`/usr/bin:/bin:/usr/sbin:/sbin`)엔 `claude` 위치(`/Users/jimmy/.local/bin`)가 **없음** |
| 3 | `src/synapse_memory/llm/claude.py:33,69-87` (수정 전) | `CLAUDE_BIN = "claude"` → `shutil.which("claude")` 가 PATH 의존 → 데몬 환경에서 `None` 반환 |
| 4 | `src/synapse_memory/llm/claude.py:90-92,378-379` | `claude_path is None` → `_complete_envelope()` 준비 단계에서 `ClaudeUnavailableError("Claude Code CLI 미설치")` 발생 |
| 5 | `src/synapse_memory/wiki/ingest.py:113-121` | 예외난 doc은 watermark를 전진시키지 않음. 이번 장애처럼 25개 전부 실패하면 watermark `2026-06-12` 고정, `pages=0` |
| 6 | `src/synapse_memory/cli.py:710-722` (`cmd_watch_run`, 수정 전) | `result.errors`를 **출력하지 않음** → 로그엔 `docs=25, pages=0`만 남고 진짜 에러는 묻힘 (1주일간 미발견 이유) |

### 핵심 증거

```text
# launchd PATH vs claude 위치
$ launchctl getenv PATH          → (빈 값)
$ command -v claude              → /Users/jimmy/.local/bin/claude
# launchd 기본 PATH 어디에도 claude 없음

# 수동 ingest (셸 PATH = ~/.local/bin 포함) → 성공
$ synapse-memory ingest --source claude-code --limit 1
ingest claude-code: docs=1, pages=1
  written: ms-videoplayer-ios

# 데몬 경로(launchd PATH)에서만 실패 → 차이는 PATH 단 하나
```

`docs=25` 가 매 사이클 동일한 이유: 이번 장애에서는 `max_docs_per_cycle=25` 캡에 걸린
배치가 전부 실패했고 watermark가 전진하지 않아 **같은 백로그 앞부분 25개를 무한 재시도**했다.
혼합 성공/실패 배치에서는 성공한 뒤쪽 doc 때문에 watermark가 전진할 수 있으므로, 이 설명은
"배치 전부 실패" 상황에 한정된다.

---

## 3. 영향 범위

- vault 갱신 완전 중단 (claude-code 소스)
- raw 백로그 누적: `~/.synapse/private/raw` 전체 6351개 파일, watermark 이후분 미처리
- 사용자에게 무증상 — 로그가 정상처럼 보임(`docs=25, pages=0`), `/sm:doctor`도 ✓

---

## 4. 개선 방향

> 2026-06-19 재검토 결과: 4.1, 4.2, 4.3 및 회귀 테스트는 코드에 적용했다.
> 4.4는 사용자 로컬 LaunchAgent 재설치 작업이라 코드에서 자동 실행하지 않았다.
> 4.5, 4.6은 후속 운영/doctor 개선 항목으로 남긴다.

### 4.1 [필수] plist에 PATH 주입 — `build_plist` (`wiki/launchd.py`)

`EnvironmentVariables.PATH` 를 plist에 박는다. resolved 바이너리 디렉터리 + 설치 시점
셸 PATH 중 안정적인 bin 경로 + 표준 디렉터리를 병합한다. 임시 경로(`.codex/tmp`, `/tmp`,
`/private/var/folders` 등)는 plist에 영구 저장하지 않는다.

```python
import os

_STANDARD_PATHS = ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")
_USER_BIN_SUFFIXES = ("bin", ".local/bin", ".cargo/bin", ".npm/bin", ".bun/bin")
_UNSTABLE_PATH_MARKERS = ("/.codex/tmp/", "/.venv/", "/node_modules/", "/private/tmp/",
                          "/private/var/folders/", "/tmp/", "/var/tmp/")


def _known_user_bin_paths() -> tuple[str, ...]:
    home = os.path.normpath(os.path.expanduser("~"))
    return tuple(os.path.join(home, suffix) for suffix in _USER_BIN_SUFFIXES)


def _is_persistent_path(path: str) -> bool:
    normalized = os.path.normpath(os.path.expanduser(path))
    if not os.path.isabs(normalized):
        return False
    return not any(marker in f"{normalized}/" for marker in _UNSTABLE_PATH_MARKERS)


def _daemon_path(program_args: list[str]) -> str:
    """데몬용 PATH — resolved 바이너리 dir + 알려진 user/system bin 병합."""
    parts: list[str] = []
    bin_path = program_args[0] if program_args else ""
    if os.path.isabs(bin_path):
        bin_dir = os.path.dirname(bin_path)
        if _is_persistent_path(bin_dir):
            parts.append(bin_dir)
    claude = shutil.which("claude")
    if claude:
        claude_dir = os.path.dirname(claude)
        if _is_persistent_path(claude_dir):
            parts.append(claude_dir)
    parts.extend(_known_user_bin_paths())
    parts.append("/opt/homebrew/bin")
    parts.extend(_STANDARD_PATHS)
    seen, out = set(), []
    for p in parts:
        normalized = os.path.normpath(os.path.expanduser(p))
        if _is_persistent_path(normalized) and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return os.pathsep.join(out)


def build_plist(*, program_args: list[str], interval_seconds: int) -> str:
    payload = {
        "Label": LABEL,
        "ProgramArguments": list(program_args),
        "StartInterval": int(interval_seconds),
        "ThrottleInterval": int(interval_seconds),
        "RunAtLoad": False,
        "EnvironmentVariables": {"PATH": _daemon_path(program_args)},  # ← 추가
        "StandardOutPath": str(l0_root() / "watch.out.log"),
        "StandardErrorPath": str(l0_root() / "watch.err.log"),
    }
    return plistlib.dumps(payload).decode("utf-8")
```

**주의:** 설치 시점 `PATH` 전체를 plist에 영구 저장하지 않는다. 사용자가 비표준 위치에
`claude`를 두면 `shutil.which("claude")` 로 resolved dir만 병합하고, 임시/venv 경로는 제외한다.
테스트는 `home=` 격리 + `_launchctl` monkeypatch 유지, 임시 PATH 제외 여부를 함께 확인한다.

### 4.2 [필수] `claude` 탐색에 폴백 추가 — `detect_claude_environment` (`llm/claude.py:69`)

PATH 누락 환경에서도 동작하도록 `shutil.which` 실패 시 알려진 경로 폴백.

```python
def detect_claude_environment(model: str = DEFAULT_MODEL) -> ClaudeEnvironment:
    path = shutil.which(CLAUDE_BIN)
    if path is None:
        for cand in (
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
        ):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                path = cand
                break
    ...
```

4.1 또는 4.2 단독으로도 복구되나, **둘 다** 적용해 방어 이중화 권장.

### 4.3 [필수] 에러 가시성 — `cmd_watch_run` (`cli.py:710-722`)

`result.errors`를 stderr로 출력 → launchd가 `watch.err.log`에 기록 → 재발 시 즉시 탐지.
에러가 있으면 `watch run`은 1을 반환한다. 단, 부분 성공 사이클도 실패 종료로 보이므로
운영 로그에서는 `watch.out.log`의 `pages`와 `errors`를 함께 봐야 한다.

```python
def cmd_watch_run(args: argparse.Namespace) -> int:
    outcome = run_watch_cycle()
    if not outcome.ran:
        print(f"skipped: {outcome.skipped_reason}")
        return 0
    result = outcome.result
    pages = getattr(result, "pages_written", []) or []
    docs = getattr(result, "docs_processed", 0)
    errors = getattr(result, "errors", []) or []
    print(f"watch run: docs={docs}, pages={len(pages)}, errors={len(errors)}")
    if pages:
        print("  written: " + ", ".join(pages))
    for e in errors:                              # ← 추가
        print(f"  error: {e}", file=sys.stderr)
    return 1 if errors else 0                      # ← 비정상 종료코드로 launchd 가시화
```

### 4.4 [필수] 기존 설치 즉시 복구 (코드 수정 후)

코드는 수정됐지만 기존 plist는 자동으로 재작성되지 않는다. 아래 재설치가 필요하다.

```bash
synapse-memory watch uninstall
synapse-memory watch install      # 새 build_plist로 PATH 포함 plist 재생성
```

또는 다음 사이클 기다리지 말고 1회 수동 트리거:

```bash
synapse-memory watch run          # 또는 launchctl kickstart -k gui/$(id -u)/com.synapse-memory.watch
```

### 4.5 [선택] 백로그 드레인

watermark가 `2026-06-12`에 멈춰 7일치 raw 누적. 정상화 후에도 `max_docs_per_cycle=25` ×
20분 주기로는 소진이 느림.

```bash
synapse-memory backfill --source claude-code   # 배치 단위 일괄 처리 (재개 가능)
```

또는 `~/.synapse/config.yaml`의 `maintenance.max_docs_per_cycle` 일시 상향 후 원복.

### 4.6 [선택] doctor 강화 — `sm:doctor`

설치 검사뿐 아니라 **마지막 성공 ingest 시각 / watermark 신선도 / watch.err.log 최근 에러**를
점검 항목에 추가. 현재 doctor가 ✓만 띄워 무증상 실패를 못 잡음.

---

## 5. 검증 절차 (수정 후)

1. `synapse-memory watch uninstall && synapse-memory watch install`
2. plist에 `EnvironmentVariables.PATH` 포함 확인:
   `plutil -p ~/Library/LaunchAgents/com.synapse-memory.watch.plist | grep -A3 Environment`
3. 수동 1회: `synapse-memory watch run` → `pages>0` 또는 `errors=0` 확인
4. watermark 전진 확인:
   `python3 -c "import sys; sys.path.insert(0,'src'); from synapse_memory.wiki.watermark import load_watermark; print(load_watermark('claude-code'))"`
   → `2026-06-12` 보다 큰 값
5. vault에 신규/갱신 페이지 mtime 확인
6. 20분 후 `watch.out.log`에 `pages>0` 사이클 등장 확인

---

## 6. 변경 파일 요약

| 파일 | 변경 | 우선순위 |
|---|---|---|
| `src/synapse_memory/wiki/launchd.py` | `build_plist`에 `EnvironmentVariables.PATH` 추가 (`_daemon_path` 헬퍼) | 적용됨 |
| `src/synapse_memory/llm/claude.py` | `detect_claude_environment` 경로 폴백 | 적용됨 |
| `src/synapse_memory/cli.py` | `cmd_watch_run` 에러 출력 + 종료코드, watch help 문구 StartInterval로 정정 | 적용됨 |
| `tests/` | 위 3건 회귀 테스트 (plist PATH 포함 / which 폴백 / errors 출력) | 적용됨 |
| `sm:doctor` 스킬 | watermark 신선도·err 로그 점검 추가 | 선택 |

---

## 7. 회귀 테스트 포인트

- `build_plist` 결과 plist에 `EnvironmentVariables.PATH` 존재 + `claude` dir 포함 (monkeypatch `os.environ`, `shutil.which`)
- `detect_claude_environment`: `shutil.which`→None 일 때 폴백 경로 발견 (tmp 실행파일 + monkeypatch)
- `cmd_watch_run`: `result.errors` 비었을 때 rc=0, 있을 때 rc=1 + stderr 출력 (`run_watch_cycle` monkeypatch)
