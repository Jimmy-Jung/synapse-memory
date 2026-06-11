# 구현 계획: Hook Context Injection

> 저자: JunyoungJung  
> 작성일: 2026-06-11  
> 브랜치: `release/1.16.1`  
> 상태: IMPLEMENTATION

## 요약

Spec 018은 `/sm:setup`의 정적 marker 방식만으로는 Claude Code 세션 컨텍스트가
stale해지고, `CLAUDE.md`에 개인 컨텍스트가 남는 문제를 줄이기 위한 하이브리드
개선이다. 이번 release의 구현 단위는 M1로 제한한다.

Claude Code에는 `SessionStart` hook을 설치할 수 있으므로 등록 프로젝트에서 세션
시작 시 `~/.synapse/context/rendered.md`를 stdout으로 내보내 additional context로
주입한다. Codex는 hook이 없으므로 기존 `AGENTS.md` marker 경로를 유지한다.

## 범위

### 포함

- `projects.yaml` 저장 시 hook용 `projects.json` sidecar 병행 생성.
- `render_context_cache()` 추가: Profile/DecisionPatterns 요약을 `rendered.md`에
  2KB 이하로 사전 렌더.
- `synapse_memory.hooks.session_start` 추가: stdlib-only hook runner.
- `synapse_memory.hooks.install` 추가: Claude Code `settings.json`에 SessionStart
  hook을 멱등 install/uninstall.
- `synapse-memory hook install|uninstall|run --event session-start` CLI.
- `setup`/`sync` 후 context cache 갱신.
- `synapse-memory context render` CLI: marker 재작성 없이 hook context cache만 갱신.
- `/sm:apply-profile` 승인 반영 후 `context render` 실행 안내.
- `synapse-memory setup --no-marker`: AGENTS/CLAUDE marker 없이 registry + hook cache만 등록.
- `synapse-memory setup --target codex`: Codex용 `AGENTS.md` marker만 등록/갱신.
- `synapse-memory doctor`에 Claude Code SessionStart hook 설치 상태 진단 추가.
- 미등록 git repo에서 opt-in suggest_register 안내 (`hook.suggest_register=true`).
- Claude settings.json 원자적 기록 및 CLI fast-path용 `E402` noqa 범위 축소.
- `~/.synapse/context/settings.json` sidecar: hook runner가 stdlib-json만으로
  `enabled` / `suggest_register` / `max_inject_bytes` 설정을 읽는다.

### 제외

- `sync`를 Codex marker 전용으로 축소.
- 미등록 프로젝트 제안의 기본 활성화.
- marker 제거 마이그레이션.

## Pseudocode

```text
save_registry(entries, projects.yaml):
    기존 yaml atomic write
    projects.json sidecar atomic write

render_context_cache(profile, patterns):
    body = generate_marker_body(profile, patterns)
    body = utf8_truncate(body, max_bytes=2048)
    write ~/.synapse/context/rendered.md with private file mode

hook run:
    cwd = Path.cwd()
    projects = json.load(~/.synapse/projects.json)
    if cwd is not under active project path:
        return 0 with no output
    if rendered.md exists:
        stdout(rendered bytes[:2048])
    else:
        stdout(fallback one-line message)
    return 0

hook install:
    settings = ~/.claude/settings.json or {}
    if command exists: no-op
    append SessionStart command hook
    write settings

context render:
    vault = configured vault path
    profile, patterns = configured AI profile paths
    render_context_cache(profile, patterns)
    render hook settings sidecar

apply-profile:
    approved facts/patterns are written to vault
    candidate status becomes applied
    run synapse-memory context render

setup --no-marker:
    register cwd with target="hook"
    skip marker file writes
    render hook context cache

hook unregistered cwd:
    if suggest_register disabled:
        stdout nothing
    if enabled and cwd is inside git repo and not suggested before:
        stdout one-line setup --no-marker hint

hook settings:
    config set hook.suggest_register true
    setup/sync/context render writes ~/.synapse/context/settings.json
    session_start.py reads only stdlib JSON sidecar

doctor:
    inspect ~/.claude/settings.json SessionStart hooks
    print installed/missing + install command
```

## 보안 / 성능

- hook runner는 stdlib만 사용하고 모든 예외를 삼켜 세션 시작을 막지 않는다.
- hook은 LLM 호출, RAG 검색, yaml parsing을 하지 않는다.
- hook 출력은 최대 2KB로 제한한다.
- `rendered.md`는 `~/.synapse/context/` 아래 `0600` 파일로 저장한다.

## 검증

```text
uv run pytest \
  tests/test_projects_registry.py \
  tests/test_projects_summary.py \
  tests/test_hooks_session_start.py \
  tests/test_hooks_install.py \
  tests/test_cli_setup_sync.py \
  tests/test_rag_cli.py
```
