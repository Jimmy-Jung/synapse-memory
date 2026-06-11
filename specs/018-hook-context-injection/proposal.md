# Spec 018 — Hook 기반 자동 프로젝트 컨텍스트 주입

> `/sm:setup`의 정적 marker 방식을 Claude Code SessionStart hook 기반 동적 주입으로
> 개선. 등록 프로젝트에서 세션 시작 시 Profile/DecisionPatterns 요약이 자동으로
> 컨텍스트에 들어온다. Codex는 hook이 없으므로 marker 경로를 유지하는 하이브리드.
>
> 저자: JunyoungJung
> 작성일: 2026-06-11
> 상태: PROPOSAL
> 관련: spec 013 (SM Setup/Sync), spec 012 (Private Permissions), spec 017 (Knowledge Compounding)

---

## 1. 배경과 문제

### 1.1 현재 구조 (spec 013)

```
/sm:setup  (프로젝트마다 수동 1회)
  ├─ generate_marker_body(Profile.md, DecisionPatterns.md)   # projects/summary.py
  ├─ inject_or_replace(CLAUDE.md), inject_or_replace(AGENTS.md)  # projects/marker.py
  │     <!-- SYNAPSE-MEMORY START --> ... <!-- SYNAPSE-MEMORY END -->
  └─ upsert_entry(~/.synapse/projects.yaml)                  # projects/registry.py

/sm:sync   (Profile 변경 후 수동 호출)
  └─ projects.yaml의 모든 entry → marker body 재생성·교체
```

### 1.2 문제 3개

| # | 문제 | 영향 |
|---|---|---|
| F1 | **수동 마찰** — 프로젝트마다 `/sm:setup` 직접 실행. 깜빡하면 컨텍스트 없이 작업 | 신규 프로젝트 누락 상시 발생 |
| F2 | **Staleness** — marker는 정적 텍스트. Profile 갱신 후 `/sm:sync` 잊으면 낡은 컨텍스트 제공 | AI가 구버전 성향 정보로 동작 |
| F3 | **프라이버시 누출** — `CLAUDE.md`는 보통 git 커밋 대상. 개인 Profile fact가 marker로 박혀 팀 repo에 노출 | spec 012(Private Permissions) 철학과 충돌. 실질 결함 |

### 1.3 해결 아이디어

Claude Code의 **SessionStart hook**은 세션 시작마다 스크립트를 실행하고 stdout을
`additionalContext`로 주입한다. 이를 이용하면:

- 주입이 **세션 시점에 동적으로** 일어남 → F2 소멸 (sync 불필요)
- repo 파일에 아무것도 쓰지 않음 → F3 소멸
- 전역 hook 1회 설치로 모든 등록 프로젝트 커버 → F1 해소 (등록만 하면 됨)

단, **Codex CLI에는 hook 시스템이 없다** → AGENTS.md marker 경로는 Codex 용으로
유지. 하이브리드가 현실적 상한선.

---

## 2. 목표 / 비목표

### 목표
- G1: Claude Code 세션 시작 시 등록 프로젝트면 Profile/Patterns 요약 자동 주입
- G2: hook 실행 비용 < 50ms, LLM 0콜, 무거운 import 0
- G3: 등록 프로젝트의 `CLAUDE.md`에서 marker 제거 가능 (개인정보 비노출)
- G4: Codex 사용 프로젝트는 기존 marker 흐름 그대로 동작
- G5: 미등록 프로젝트 자동 인식 → 등록 제안 (opt-in)

### 비목표
- Codex용 hook 대체물 개발 (Codex가 지원할 때 재검토)
- marker 메커니즘 제거 (Codex 의존 + fallback으로 존속)
- hook에서 RAG 검색 실행 (비용·레이턴시 — 요약 캐시만 읽는다)

---

## 3. 아키텍처

### 3.1 현재 (정적 — push 모델)

```
Profile.md 변경
   ↓ (사용자가 기억해야 함)
/sm:sync ──▶ 등록 프로젝트 N개의 CLAUDE.md / AGENTS.md marker 재작성
   ↓
세션 시작 ──▶ CLAUDE.md 통째로 로드 (marker 포함, git에도 노출)
```

### 3.2 제안 (동적 — pull 모델, 하이브리드)

```
Profile.md / DecisionPatterns.md 변경
   ↓
daily update_profile stage 또는 /sm:sync
   └─▶ render_context_cache() ──▶ ~/.synapse/context/rendered.md   (사전 렌더 1회)

[Claude Code]                          [Codex]
세션 시작                               세션 시작
   ↓                                      ↓
SessionStart hook (stdlib-only)         AGENTS.md marker 로드 (기존 그대로)
   ├─ cwd ∈ projects.yaml ?
   │    ├─ 아니오 → exit 0 (무출력)          ※ /sm:setup --target codex 로 축소
   │    └─ 예 ↓
   ├─ rendered.md 읽기 (파일 1개)
   └─ stdout → additionalContext 주입   ✅ 항상 최신, repo 무오염
```

핵심 결정:
- **hook은 읽기 전용 + stdlib-only.** 렌더링(요약 생성)은 daily/sync가 미리 수행.
  hook 자체는 yaml 파싱도 안 한다 — registry를 JSON sidecar로 병행 저장해
  `json` 모듈만 사용.
- **실패는 침묵.** hook 오류가 세션 시작을 막으면 안 됨 — 모든 예외 → exit 0.
- **크기 상한.** 주입 본문 ≤ 2KB. 초과분은 자르고 "상세: `/sm:ask`" 포인터.

---

## 4. 폴더·파일 구조

### 4.1 신규/변경 파일

```
~/.synapse/
├── projects.yaml                  # 기존 (사람 편집 가능 원본)
├── projects.json                  # 🆕 hook용 sidecar — save_registry()가 병행 기록
└── context/
    └── rendered.md                # 🆕 사전 렌더된 주입 본문 (≤2KB)

~/.claude/settings.json            # 🆕 hook install이 SessionStart entry 추가

src/synapse_memory/
├── projects/
│   ├── registry.py                # 수정: save_registry()가 projects.json 병행 기록
│   ├── summary.py                 # 수정: render_context_cache() 추가
│   └── marker.py                  # 유지 (Codex 경로)
├── hooks/                         # 🆕
│   ├── __init__.py
│   ├── install.py                 # settings.json에 hook 등록/제거
│   └── session_start.py           # hook 본체 — stdlib-only 제약
└── cli.py                         # 수정: hook install/uninstall/run 서브커맨드
```

### 4.2 settings.json에 추가되는 entry

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "synapse-memory hook run --event session-start",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

> 참고: `synapse-memory` entry point가 패키지 전체를 import하면 느리므로,
> `hook run`은 cli.py 최상단에서 **조기 분기** — 무거운 모듈 import 전에
> `hooks/session_start.py`만 실행하고 종료한다 (§6.3).

---

## 5. 플로우

### 5.1 설치 (전역 1회)

```
synapse-memory hook install
  ├─ ~/.claude/settings.json 읽기 (없으면 생성)
  ├─ SessionStart에 synapse entry 존재? → 있으면 no-op (멱등)
  ├─ entry 추가 + 백업 (settings.json.bak)
  ├─ projects.yaml → projects.json sidecar 생성
  └─ render_context_cache() 1회 실행
```

### 5.2 세션 시작 (매번, 자동)

```
Claude Code 세션 시작 (아무 디렉토리)
  ↓
hook: session_start.py
  ├─ projects.json 로드 (json, stdlib)            ~1ms
  ├─ cwd가 등록 path의 하위인가? (prefix 매칭)      ~0ms
  │    ├─ 아니오:
  │    │    ├─ suggest_register=false → exit 0 (무출력, 기본값)
  │    │    └─ true → 1줄 힌트 출력 후 exit 0
  │    └─ 예 ↓
  ├─ ~/.synapse/context/rendered.md 읽기            ~1ms
  │    └─ 없으면: 1줄 fallback ("/sm:sync로 컨텍스트 캐시 생성") 출력
  └─ stdout으로 본문 출력 → additionalContext 주입
```

### 5.3 Profile 갱신 시 (staleness 소멸)

```
/sm:apply-profile 로 Profile.md 변경
  ↓
같은 명령 끝에서 render_context_cache() 자동 호출   # 🆕 1줄 추가
  ↓
다음 세션부터 즉시 최신 반영 (sync 불필요)

Codex 프로젝트만: /sm:sync가 AGENTS.md marker 갱신 (기존 동작 유지)
```

### 5.4 미등록 프로젝트 자동 인식 (G5, opt-in)

```
hook에서 cwd 미등록 && suggest_register=true && git repo 감지
  ↓
출력: "Synapse Memory: 이 프로젝트는 미등록. /sm:setup 으로 등록하면
       Profile 컨텍스트가 자동 주입됩니다."  (1줄, 세션당 1회)
  ↓
사용자가 /sm:setup 실행 → projects.yaml + projects.json 등록
  ↓ (이때 Claude Code 전용이면)
  --no-marker 옵션: CLAUDE.md 수정 없이 registry 등록만   # 🆕 F3 해결
```

자동 등록(무확인)은 채택하지 않음 — 어떤 프로젝트를 second brain에 연결할지는
사용자 결정 사항 (spec 012 승인 철학).

---

## 6. 예시 코드

### 6.1 `hooks/session_start.py` — hook 본체 (stdlib-only)

```python
"""SessionStart hook — 등록 프로젝트에 컨텍스트 주입.

제약: stdlib만 사용 (yaml/chromadb 등 금지 — 콜드스타트 <50ms 목표).
실패는 전부 침묵 (exit 0) — 세션 시작을 막지 않는다.

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SYNAPSE_HOME = Path(os.environ.get("SYNAPSE_HOME", "~/.synapse")).expanduser()
REGISTRY_JSON = SYNAPSE_HOME / "projects.json"
RENDERED = SYNAPSE_HOME / "context" / "rendered.md"
MAX_BYTES = 2048

FALLBACK = (
    "Synapse Memory: 컨텍스트 캐시 없음 — `/sm:sync` 실행으로 생성 가능."
)


def _registered_root(cwd: Path) -> str | None:
    """cwd가 등록 프로젝트(하위 포함)면 그 root 경로 반환."""
    try:
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in data.get("projects", []):
        if entry.get("state") != "active":
            continue
        root = Path(entry.get("path", "")).expanduser()
        if root and cwd.is_relative_to(root):
            return str(root)
    return None


def main() -> int:
    try:
        cwd = Path.cwd().resolve()
        if _registered_root(cwd) is None:
            return 0  # 미등록 — 무출력 (suggest는 config 확장으로)
        try:
            body = RENDERED.read_bytes()[:MAX_BYTES].decode(
                "utf-8", errors="ignore"
            )
        except OSError:
            body = FALLBACK
        sys.stdout.write(body)
        return 0
    except Exception:
        return 0  # 어떤 실패도 세션을 막지 않는다


if __name__ == "__main__":
    raise SystemExit(main())
```

### 6.2 `projects/summary.py` 확장 — 캐시 렌더

```python
RENDERED_MAX_BYTES = 2048


def render_context_cache(
    profile_path: Path,
    patterns_path: Path,
    *,
    out_path: Path | None = None,
) -> Path:
    """Profile/Patterns → hook 주입용 캐시 파일 사전 렌더.

    generate_marker_body()와 동일 소스를 쓰되, 세션 주입용으로
    2KB 상한을 강제한다.
    """
    out = out_path or _synapse_home() / "context" / "rendered.md"
    body = generate_marker_body(profile_path, patterns_path)
    encoded = body.encode("utf-8")
    if len(encoded) > RENDERED_MAX_BYTES:
        truncated = encoded[:RENDERED_MAX_BYTES].decode("utf-8", errors="ignore")
        body = truncated + "\n\n(요약 일부 — 상세: `/sm:ask`)"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return out
```

호출 지점 (각 1줄 추가):
- `daily.py` `update_profile` stage 성공 직후
- `/sm:apply-profile` 반영 직후
- `/sm:sync` (Codex marker 갱신과 함께)

### 6.3 `cli.py` 조기 분기 — 콜드스타트 회피

```python
# cli.py 최상단, 무거운 import 이전
def _fast_path_hook() -> None:
    """`synapse-memory hook run ...`은 패키지 import 없이 즉시 처리."""
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "hook" and sys.argv[2] == "run":
        from synapse_memory.hooks.session_start import main
        raise SystemExit(main())


_fast_path_hook()

# ↓ 이하 기존 무거운 import (yaml, click, ...)
```

### 6.4 `registry.py` 수정 — JSON sidecar 병행 기록

```python
def save_registry(entries: list[ProjectEntry], registry_path: Path) -> None:
    # ... 기존 yaml atomic write 그대로 ...
    _save_json_sidecar(entries, registry_path.with_suffix(".json"))


def _save_json_sidecar(entries: list[ProjectEntry], path: Path) -> None:
    """hook(stdlib-only)이 yaml 없이 읽을 수 있는 사본. 원본은 yaml."""
    payload = {
        "version": 1,
        "projects": [_entry_to_dict(e) for e in entries],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, path)
```

### 6.5 `hooks/install.py` (발췌) — settings.json 멱등 설치

```python
HOOK_COMMAND = "synapse-memory hook run --event session-start"


def install_session_hook(settings_path: Path | None = None) -> bool:
    """~/.claude/settings.json에 SessionStart hook 등록. 멱등.

    Returns:
        True면 신규 설치, False면 이미 존재 (no-op).
    """
    path = settings_path or Path.home() / ".claude" / "settings.json"
    settings = (
        json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    )
    session_hooks = settings.setdefault("hooks", {}).setdefault(
        "SessionStart", []
    )
    for group in session_hooks:
        for h in group.get("hooks", []):
            if h.get("command") == HOOK_COMMAND:
                return False  # 이미 설치됨

    if path.is_file():
        path.with_suffix(".json.bak").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    session_hooks.append(
        {"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 5}]}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True
```

---

## 7. `/sm:setup` · `/sm:sync` 역할 변화

| 명령 | 현재 | 제안 후 |
|---|---|---|
| `/sm:setup` | CLAUDE.md + AGENTS.md marker 주입 + registry 등록 | registry 등록 중심. `--target codex`만 AGENTS.md marker. Claude Code 전용이면 `--no-marker` (repo 무오염) |
| `/sm:sync` | 전체 프로젝트 marker 재작성 | ① 캐시 재렌더 (Claude Code용) ② Codex 프로젝트만 marker 재작성 |
| `synapse-memory hook install` | — | 🆕 전역 hook 설치 (멱등) |
| `synapse-memory hook uninstall` | — | 🆕 entry 제거 + 백업 복원 안내 |
| `synapse-memory hook run` | — | 🆕 hook 본체 (사용자 직접 호출 비대상) |

기존 사용자 마이그레이션: `hook install` 후 안내 — "등록 프로젝트의 CLAUDE.md
marker는 이제 불필요. `synapse-memory setup --remove-marker <path>`로 정리 가능
(AGENTS.md는 Codex 쓰면 유지)."

---

## 8. 설정 추가 (config.py)

```python
@dataclass
class HookConfig:
    """SessionStart hook 동작 설정."""

    enabled: bool = True
    max_inject_bytes: int = 2048
    # 미등록 프로젝트에서 등록 제안 1줄 출력 여부 (기본 끔 — 소음 방지)
    suggest_register: bool = False
```

---

## 9. 엣지 케이스

| 케이스 | 동작 |
|---|---|
| rendered.md 없음 (첫 설치 직후) | fallback 1줄 출력. install이 즉시 1회 렌더하므로 정상 경로에선 발생 안 함 |
| projects.json 없음 / 파손 | exit 0 무출력. 다음 save_registry()가 재생성 |
| settings.json에 다른 도구 hook 공존 | install은 entry append만 — 기존 hook 불변. uninstall은 자기 entry만 제거 |
| cwd가 등록 path의 하위 디렉토리 | `is_relative_to`로 root 매칭 — 주입됨 |
| 같은 프로젝트 중첩 등록 (parent+child) | 첫 매칭 root 사용. setup 시 중첩 감지·경고 |
| hook 실행 환경에 synapse-memory 미설치 (PATH 문제) | timeout 5s + 스크립트는 모든 예외 exit 0 — 세션 시작 불가침 |
| Codex만 쓰는 프로젝트 | hook 무관 — AGENTS.md marker 기존 흐름 |
| 사용자가 hook을 수동 삭제 | doctor가 감지 → "hook 미설치" 안내 (doctor 체크 항목 추가) |

---

## 10. 보안·프라이버시

- rendered.md는 **이미 사용자 승인된** Profile.md/DecisionPatterns.md에서만 생성
  (MemoryInbox 후보 미포함) — 기존 승인 모델 불변.
- rendered.md 위치는 `~/.synapse/` 하위 — spec 012 권한 정책(0700) 적용 대상.
- repo 파일(CLAUDE.md)에서 개인정보 marker 제거 가능 → 노출면 감소 (F3 해결).
- hook 출력은 로컬 Claude Code 세션 컨텍스트로만 — 외부 전송 없음.

---

## 11. 도입 순서 (마일스톤)

```
M1 — 캐시 + hook 본체                                  예상 규모: 소
  ├─ summary.render_context_cache() + 호출 지점 3곳
  ├─ registry JSON sidecar
  ├─ hooks/session_start.py + cli 조기 분기
  └─ hook install/uninstall
  ✓ 검증: 등록 프로젝트 새 세션에서 Profile 요약 주입 확인
  ✓ 검증: time synapse-memory hook run < 50ms

M2 — setup/sync 역할 정리                              예상 규모: 소
  ├─ setup --no-marker / --target codex / --remove-marker
  ├─ sync = 캐시 렌더 + Codex marker만
  └─ doctor에 hook 설치 상태 체크 추가
  ✓ 검증: marker 제거 후에도 세션 컨텍스트 동일

M3 — 자동 인식 제안 (G5, opt-in)                       예상 규모: 소
  └─ suggest_register 구현 (git repo 감지 + 세션당 1회)
  ✓ 검증: 미등록 git 프로젝트에서 힌트 1줄, 일반 디렉토리에선 무출력
```

---

## 12. 비채택 결정

| 항목 | 사유 |
|---|---|
| 무확인 자동 등록 | 어떤 프로젝트를 brain에 연결할지는 사용자 결정 (spec 012 철학) |
| hook에서 RAG 실시간 검색 | 콜드스타트 비용 + chromadb import 무거움. 사전 렌더 캐시로 충분 |
| marker 완전 폐지 | Codex에 hook 없음. 하이브리드가 상한선 |
| UserPromptSubmit hook 사용 | 매 프롬프트마다 실행 — 과잉. 세션당 1회(SessionStart)면 충분 |
| projects.yaml을 JSON으로 전환 | 사람 편집 호환성 유지. sidecar 병행이 안전 |
