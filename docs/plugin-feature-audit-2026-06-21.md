# Synapse Memory 플러그인 기능 감사

저자: JunyoungJung  
작성일: 2026-06-21

## 목적

가장 기본적인 SessionStart hook과 Codex/Claude 플러그인 skill 표면이 실제
`synapse-memory` CLI와 일치하는지 검토하고, 설치된 플러그인이 read-only 상태
점검을 안정적으로 수행할 수 있는지 확인한다.

## 감사 범위

| 영역 | 확인 항목 | 결과 |
| --- | --- | --- |
| Hook | `synapse-memory hook install`, `hook run --event session-start`, `doctor` hook 진단 | 정상 동작 확인 |
| Runtime | `synapse-memory --version`, `doctor`, `config validate`, `config show --json` | 정상 동작 확인 |
| Context | `context render`, SessionStart hook context 출력 | 정상 동작 확인 |
| Watch | `watch status --json`, `doctor` watch 진단 | 실행 가능. Codex watermark stale 경고는 남음 |
| Ingest | `ingest-audit --source <source> --limit N` | 정상 동작 확인 |
| Ingest JSON | `ingest-audit --json` | 수정 후 지원 |
| Card | `card list` | 정상 동작 확인 |
| Card JSON | `card list --json` | 수정 후 지원 |
| Assistant | `assistant-status`, `assistant-status --json` | 정상 동작 확인 |
| Cleanup | `cleanup scan`, `cleanup apply` | 정상 동작 확인 |
| Cleanup 호환 옵션 | `cleanup scan --dry-run`, `cleanup apply --dry-run` | 수정 후 지원 |
| Cost | `cost summary --days 7 --json` | 정상 동작 확인 |
| Daily 상태 | `daily-status --json` | 정상 동작 확인 |
| Profile 대기열 | `list-pending-profiles --json`, `dismiss-list --json` | 정상 동작 확인 |
| Ledger | `ledger-show --json` | 정상 동작 확인. 개인 데이터가 포함되므로 공유 금지 |
| Codex manifest | `.codex-plugin/plugin.json`, `plugins/sm/.codex-plugin/plugin.json` | 1.19.0으로 정렬 |
| Claude manifest | `.claude-plugin/plugin.json` | 1.19.0으로 정렬 |
| Marketplace | `.agents/plugins/marketplace.json` local wrapper source | 1.19.0으로 정렬 |
| Skills | root `skills/`와 wrapper `plugins/sm/skills/` | 실제 CLI 명령으로 정렬 및 동기화 |

## 발견 및 조치

### 존재하지 않는 top-level CLI를 안내하던 skill

다음 skill은 실제 CLI에 없는 명령을 안내하고 있었다.

- `synapse-memory recall`
- `synapse-memory resume`
- `synapse-memory decide`
- `synapse-memory assistant`
- `synapse-memory onboard`
- `synapse-memory config "<자연어 지시>"`
- `synapse-memory cleanup`

실제 지원 명령으로 수정했다.

- `synapse-memory persona what-did-i-think`
- `synapse-memory persona draft-resume`
- `synapse-memory persona decide`
- `synapse-memory assistant-status`
- `synapse-memory config show|get|set|validate`
- `synapse-memory cleanup scan|apply`
- onboarding skill은 전용 CLI 대신 `doctor`, `setup --dry-run`,
  `context render`, `daily --quick --dry-run`의 실제 명령 조합으로 안내

### 자동 점검에 불편한 read-only 출력

자동화와 플러그인 UI가 구조적으로 결과를 읽을 수 있도록 다음 옵션을 추가했다.

- `ingest-audit --json`
- `card list --json`
- `cleanup scan --dry-run`
- `cleanup apply --dry-run`

`cleanup scan`은 원래 항상 read-only이므로 `--dry-run`은 호환용 no-op이다.
`cleanup apply`는 기본이 dry-run이며, 실제 이동은 여전히 `--apply`가 필요하다.

### 릴리스 표면 불일치

`release/1.19.0` 브랜치에서 패키지/manifest/README installer 링크가 아직
`1.18.1`로 남아 있었다. 다음 파일을 `1.19.0`으로 정렬했다.

- `pyproject.toml`
- `src/synapse_memory/__init__.py`
- `.codex-plugin/plugin.json`
- `plugins/sm/.codex-plugin/plugin.json`
- `.claude-plugin/plugin.json`
- `.agents/plugins/marketplace.json`
- `README.md`
- `uv.lock`

## 남은 운영 확인 항목

- `doctor`의 watch 진단은 Codex watermark stale 경고를 계속 표시한다. 이는 hook
  자체 실패가 아니라 Codex raw source의 새 수집/ingest 진행 상태 문제이므로,
  `watch status --json`, `watch run --once --source codex` 또는 launchd 로그로
  별도 확인한다.
- 로그인 shell에서 `/Users/jimmy/.profile`이 존재하지 않는
  `/Users/jimmy/.cargo/env`를 source하려는 경고가 나타날 수 있다. 이 경고는
  Synapse Memory 플러그인 기능과는 별개이지만, 자동 점검 로그를 흐릴 수 있다.

## 재검증 명령

```bash
uv run synapse-memory --version
uv run synapse-memory doctor
uv run synapse-memory hook run --event session-start
uv run synapse-memory config validate
uv run synapse-memory config show --json
uv run synapse-memory context render --out /tmp/synapse-memory-hook-smoke.md
uv run synapse-memory watch status --json
uv run synapse-memory ingest-audit --source claude-code --limit 3 --json
uv run synapse-memory ingest-audit --source codex --limit 3 --json
uv run synapse-memory card list --json
uv run synapse-memory assistant-status --json
uv run synapse-memory cleanup scan --dry-run --json
uv run synapse-memory cost summary --days 7 --json
uv run synapse-memory daily-status --json
```
