# P3 — 자동화 데몬 (launchd WatchPaths + 유휴 + 락) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 executing-plans. TDD, 태스크별 커밋.

**Goal:** 사람이 `ingest --now`를 칠 필요 없이, 대화 로그가 바뀌면 자동으로 ingest가 돌게 한다 — launchd `WatchPaths`(네이티브 FSEvents, R1)가 raw 디렉터리 변화 시 `synapse-memory watch run`을 깨우고, 단일 동시성 락 아래 **유휴(settled) 파일만** 통합한다.

**Architecture:** 상주 데몬 대신 launchd가 변화 시 1회 실행하는 짧은 사이클. `run_watch_cycle`: 파일락 획득(이미 실행 중이면 skip) → `ingest_source(min_age_seconds=idle_minutes*60)`로 *최근 변경되지 않은* doc만 ingest → 락 해제. idle은 P0 `config.maintenance.idle_minutes`. 핵심 로직은 순수/주입 가능해 단위테스트하고, launchctl/플랫폼 부분만 subprocess(테스트는 mock).

**Tech Stack:** P1 `wiki/ingest.py`(`ingest_source`), P0 `config.maintenance`, `storage.l0.l0_root`, `subprocess`(launchctl), `plistlib`, `pytest`.

---

## 범위 메모

- **포함**: 단일 동시성 락, 유휴(settled) 필터, watch 사이클, launchd plist 생성/설치/제거, `watch` CLI.
- **제외**: lint(P4), 초기 백필(P5). watch 소스는 claude-code 단일(P1a와 동일).
- **플랫폼**: macOS launchd. 기존 launchd/plist 헬퍼 있으면 재사용(`grep -rn "LaunchAgents\|launchctl\|plist" src/synapse_memory` 먼저).
- **테스트 격리**: 락 경로/`ingest_fn`/`launchctl`/`home`을 주입·mock. 실제 launchctl·파일감시는 단위테스트 안 함.

---

## File Structure

- Create: `src/synapse_memory/wiki/lock.py` — `FileLock`, `LockHeldError`, `default_lock_path`.
- Modify: `src/synapse_memory/wiki/rawdoc.py` + `wiki/ingest.py` — `min_age_seconds`(settled 필터).
- Create: `src/synapse_memory/wiki/daemon.py` — `run_watch_cycle`, `CycleOutcome`.
- Create: `src/synapse_memory/wiki/launchd.py` — `LABEL`, `build_plist`, `plist_path`, `install_watch`, `uninstall_watch`, `_launchctl`.
- Modify: `src/synapse_memory/cli.py` — `watch` 서브커맨드(`run`/`install`/`uninstall`/`status`).
- Modify: `src/synapse_memory/wiki/__init__.py` — export.
- Test: `tests/test_wiki_lock.py`, `test_wiki_settled.py`, `test_wiki_daemon.py`, `test_wiki_launchd.py`, `test_cli_watch.py`.

---

## Task 1: 단일 동시성 락 (wiki/lock.py)

**Files:** Create `src/synapse_memory/wiki/lock.py`; Test `tests/test_wiki_lock.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_lock.py
"""FileLock: 단일 인스턴스 보장."""
from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.wiki.lock import FileLock, LockHeldError


def test_acquire_and_release(tmp_path: Path) -> None:
    with FileLock(tmp_path / "ingest.lock"):
        assert (tmp_path / "ingest.lock").exists()
    with FileLock(tmp_path / "ingest.lock"):  # 재획득 가능
        pass


def test_second_acquire_fails_while_held(tmp_path: Path) -> None:
    p = tmp_path / "ingest.lock"
    with FileLock(p):
        with pytest.raises(LockHeldError):
            with FileLock(p):
                pass


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path: Path) -> None:
    p = tmp_path / "ingest.lock"
    p.write_text("999999999", encoding="utf-8")  # 없는 PID
    with FileLock(p):
        pass
```

- [ ] **Step 2:** `uv run pytest tests/test_wiki_lock.py -v` → fail.
- [ ] **Step 3: implement** `src/synapse_memory/wiki/lock.py`:
  - `class LockHeldError(RuntimeError): ...`.
  - `class FileLock`: `__init__(self, path: Path)`. `acquire()`: 파일 있으면 PID 읽어 `os.kill(pid, 0)` 생존 확인 → 살아있으면 `LockHeldError`, 죽었거나 파싱 실패면 stale로 덮어씀; 없으면 생성. `os.getpid()` 기록. `release()`: 자기 소유 파일이면 삭제. `__enter__`(=acquire, self 반환)/`__exit__`(=release).
  - `default_lock_path() -> Path`: `l0_root() / "ingest.lock"`.
- [ ] **Step 4:** pass (3). **Step 5:** commit `feat(wiki): add single-instance FileLock (stale-pid reclaim)`.

---

## Task 2: 유휴(settled) 필터

**Files:** Modify `src/synapse_memory/wiki/rawdoc.py`, `wiki/ingest.py`; Test `tests/test_wiki_settled.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_settled.py
"""min_age_seconds: 최근 변경된(진행 중) 파일은 건너뛴다."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from synapse_memory.wiki.rawdoc import iter_new_raw


def _sess(root: Path, name: str, text: str) -> Path:
    f = root / f"{name}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"message": {"role": "user", "content": text}}) + "\n", encoding="utf-8")
    return f


def test_recent_file_skipped_when_min_age_set(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    recent = _sess(root, "recent", "진행 중")
    settled = _sess(root, "settled", "끝난 대화")
    now = time.time()
    os.utime(recent, (now, now))
    os.utime(settled, (now - 600, now - 600))
    docs = iter_new_raw("claude-code", since=None, root=root, min_age_seconds=180, now=now)
    texts = [d.text for d in docs]
    assert "끝난 대화" in texts and "진행 중" not in texts


def test_no_min_age_returns_all(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    _sess(root, "a", "x")
    assert len(iter_new_raw("claude-code", since=None, root=root)) == 1
```

- [ ] **Step 2:** fail. **Step 3: implement**:
  - `iter_new_raw(..., min_age_seconds: float | None = None, now: float | None = None)`: 파일 mtime이 `(now or time.time()) - min_age_seconds`보다 크면(=너무 최근) skip. `import time` 추가.
  - `ingest_source(..., min_age_seconds: float | None = None)`: `iter_new_raw`에 그대로 전달.
- [ ] **Step 4:** pass + rawdoc/ingest 회귀. **Step 5:** commit `feat(wiki): add settled (min_age) filter to skip in-progress conversations`.

---

## Task 3: watch 사이클 (wiki/daemon.py)

**Files:** Create `src/synapse_memory/wiki/daemon.py`; Test `tests/test_wiki_daemon.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_daemon.py
from __future__ import annotations
from pathlib import Path
import synapse_memory.wiki.daemon as d
from synapse_memory.wiki.ingest import IngestResult


def test_cycle_runs_ingest_with_idle_filter(tmp_path, monkeypatch) -> None:
    calls = {}
    def fake_ingest(source, **kw):
        calls["source"] = source
        calls["min_age_seconds"] = kw.get("min_age_seconds")
        return IngestResult(source=source, docs_processed=1, pages_written=["x"])
    monkeypatch.setattr(d, "ingest_source", fake_ingest)
    outcome = d.run_watch_cycle(source="claude-code", lock_path=tmp_path / "l.lock", idle_minutes=3)
    assert outcome.ran is True
    assert calls["source"] == "claude-code"
    assert calls["min_age_seconds"] == 180


def test_cycle_skips_when_locked(tmp_path, monkeypatch) -> None:
    from synapse_memory.wiki.lock import FileLock
    p = tmp_path / "l.lock"
    monkeypatch.setattr(d, "ingest_source",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출되면 안 됨")))
    with FileLock(p):
        outcome = d.run_watch_cycle(source="claude-code", lock_path=p, idle_minutes=3)
    assert outcome.ran is False
    assert outcome.skipped_reason == "locked"
```

- [ ] **Step 2:** fail. **Step 3: implement** `wiki/daemon.py`:
  - `from synapse_memory.wiki.ingest import ingest_source` (모듈 레벨 — monkeypatch용).
  - `from synapse_memory.wiki.lock import FileLock, LockHeldError, default_lock_path`.
  - `@dataclass class CycleOutcome: ran: bool; skipped_reason: str | None = None; result: object | None = None`.
  - `run_watch_cycle(*, source="claude-code", lock_path=None, idle_minutes=None, vault_path=None) -> CycleOutcome`: idle_minutes 미지정→`get_config().maintenance.idle_minutes`. lock_path 미지정→`default_lock_path()`. `try: with FileLock(lock_path): res = ingest_source(source, min_age_seconds=idle_minutes*60, vault_path=vault_path); return CycleOutcome(True, None, res)` `except LockHeldError: return CycleOutcome(False, "locked")`.
- [ ] **Step 4:** pass (2). **Step 5:** commit `feat(wiki): add run_watch_cycle (lock + idle-filtered ingest)`.

---

## Task 4: launchd plist (wiki/launchd.py)

**Files:** Create `src/synapse_memory/wiki/launchd.py`; Test `tests/test_wiki_launchd.py`.

> 먼저 `grep -rn "LaunchAgents\|launchctl\|plist" src/synapse_memory` 로 기존 헬퍼 확인 후 재사용.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_launchd.py
from __future__ import annotations
from synapse_memory.wiki.launchd import (
    LABEL, build_plist, install_watch, plist_path, uninstall_watch,
)


def test_build_plist_has_watchpaths_and_program() -> None:
    xml = build_plist(program_args=["synapse-memory", "watch", "run"],
                      watch_paths=["/home/u/.synapse/private/raw/claude-code"])
    assert "WatchPaths" in xml
    assert "watch" in xml and "run" in xml
    assert "/home/u/.synapse/private/raw/claude-code" in xml
    assert xml.lstrip().startswith("<?xml")


def test_plist_path_under_launchagents(tmp_path) -> None:
    assert plist_path(home=tmp_path) == tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def test_install_writes_plist_and_loads(tmp_path, monkeypatch) -> None:
    cmds = []
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: cmds.append(a))
    path = install_watch(home=tmp_path, program_args=["synapse-memory", "watch", "run"],
                         watch_paths=["/x/raw/claude-code"])
    assert path.is_file()
    assert cmds  # launchctl 호출됨


def test_uninstall_removes_plist(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("synapse_memory.wiki.launchd._launchctl", lambda *a: None)
    install_watch(home=tmp_path, program_args=["x"], watch_paths=["/y"])
    uninstall_watch(home=tmp_path)
    assert not plist_path(home=tmp_path).exists()
```

- [ ] **Step 2:** fail. **Step 3: implement** `wiki/launchd.py`:
  - `LABEL = "com.synapse-memory.watch"`.
  - `build_plist(*, program_args, watch_paths) -> str`: `plistlib.dumps({"Label": LABEL, "ProgramArguments": list(program_args), "WatchPaths": list(watch_paths), "RunAtLoad": False, "StandardOutPath": str(l0_root()/"watch.out.log"), "StandardErrorPath": str(l0_root()/"watch.err.log")}).decode("utf-8")`.
  - `plist_path(*, home=None) -> Path`: `(home or Path.home())/"Library"/"LaunchAgents"/f"{LABEL}.plist"`.
  - `_launchctl(*args)`: `subprocess.run(["launchctl", *args], check=False, capture_output=True)`.
  - `install_watch(*, home=None, program_args=None, watch_paths=None) -> Path`: 기본 program_args=`[shutil.which("synapse-memory") or "synapse-memory", "watch", "run"]`, 기본 watch_paths=`[str(l0_root()/"raw"/"claude-code")]`. plist_path 부모 mkdir → 파일 작성 → `_launchctl("load", "-w", str(path))`. 반환.
  - `uninstall_watch(*, home=None) -> None`: 파일 있으면 `_launchctl("unload", str(path))` 후 `path.unlink(missing_ok=True)`.
- [ ] **Step 4:** pass (4). **Step 5:** commit `feat(wiki): add launchd plist install/uninstall for watch`.

---

## Task 5: CLI `watch` + 회귀

**Files:** Modify `src/synapse_memory/cli.py`, `wiki/__init__.py`; Test `tests/test_cli_watch.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_cli_watch.py
import synapse_memory.cli as cli
from synapse_memory.wiki.daemon import CycleOutcome


def test_cli_watch_run(monkeypatch):
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=True, result=None))
    assert cli.main(["watch", "run"]) == 0


def test_cli_watch_run_skipped(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=False, skipped_reason="locked"))
    assert cli.main(["watch", "run"]) == 0
    assert "locked" in capsys.readouterr().out


def test_cli_watch_install(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "install_watch", lambda **kw: tmp_path / "x.plist")
    assert cli.main(["watch", "install"]) == 0
```

- [ ] **Step 2:** fail. **Step 3: implement** — cli.py 상단 import `from synapse_memory.wiki.daemon import run_watch_cycle`, `from synapse_memory.wiki.launchd import install_watch, uninstall_watch`. `build_parser`에 `watch` 서브파서 + `add_subparsers(dest="action")` 액션 `run`/`install`/`uninstall`/`status`. `cmd_watch_run`: `o = run_watch_cycle()`; ran이면 `print(...)` 결과 요약 else `print(f"skipped: {o.skipped_reason}")`; return 0. `cmd_watch_install`: `print(f"installed: {install_watch()}")`; return 0. `cmd_watch_uninstall`: `uninstall_watch(); print("uninstalled")`; return 0. `cmd_watch_status`: `from synapse_memory.wiki.launchd import plist_path`; 존재 여부 + 마지막 watermark(`load_watermark("claude-code")`) 출력; return 0.
- [ ] **Step 4:** `uv run pytest -q` 전체 통과 + `ruff check src/synapse_memory/wiki src/synapse_memory/cli.py tests/test_wiki_*.py tests/test_cli_watch.py` clean. **Step 5:** commit `feat(cli): add 'watch' subcommand (run/install/uninstall/status)`.

---

## Self-Review
- **Spec coverage:** spec 019 §4 자동 유지 루프 — launchd WatchPaths(R1, Task 4), 유휴 디바운스(settled 필터 Task 2), 단일 동시성 락(Task 1+3), 수동 탈출구는 P1 `ingest --now` 유지. lint(P4)/백필(P5) 제외.
- **테스트 격리:** 락 경로·ingest_fn·launchctl·home·`now`·`min_age_seconds` 주입/mock → 실제 launchctl·파일감시 없이 결정적 단위테스트.
- **Type consistency:** `FileLock`/`LockHeldError`/`default_lock_path`, `iter_new_raw(..., min_age_seconds, now)`, `ingest_source(..., min_age_seconds)`, `run_watch_cycle(*, source, lock_path, idle_minutes, vault_path)->CycleOutcome(ran, skipped_reason, result)`, `LABEL`/`build_plist(*, program_args, watch_paths)`/`plist_path(*, home)`/`install_watch`/`uninstall_watch`/`_launchctl`가 전 태스크 일관.
- **idle 연동:** `run_watch_cycle`이 `config.maintenance.idle_minutes`(P0) → `min_age_seconds=idle_minutes*60`.
