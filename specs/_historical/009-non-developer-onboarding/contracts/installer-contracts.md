# 인스톨러 계약: 비개발자용 자동 온보딩

**기능**: 009-non-developer-onboarding  
**작성일**: 2026-05-12  
**작성자**: Synapse Memory Maintainers

## `installer/SynapseMemory-Installer.command`

분류: local macOS setup entrypoint. LLM conversation endpoint가 아니다.

### 실행 계약

```bash
open installer/SynapseMemory-Installer.command
```

파일은 다음을 만족해야 한다.

- macOS에서 zsh로 실행된다.
- 사용자의 현재 shell directory에 의존하지 않고 자신의 repository/release directory를 찾는다.
- 첫 mutating step 전에 log file을 생성한다.
- 어떤 apply action보다 먼저 GUI consent prompt를 표시한다.
- 실패 시 non-zero로 종료하고 log path를 사용자가 확인할 수 있게 남긴다.

### 동의 프롬프트 계약

동의 dialog는 다음을 전달해야 한다.

- Synapse Memory가 setup에 필요한 local tool을 설치하거나 확인한다.
- Synapse Memory가 Obsidian vault를 감지하고, 사용자가 GUI에서 기존 vault 또는 새 저장소 위치를 선택할 수 있게 한다.
- iCloud Obsidian container가 있으면 새 vault 추천 위치는 iCloud의 `SynapseVault`다.
- Synapse Memory가 `~/.synapse`와 선택된 vault setup 영역에 local file을 구성한다.
- 로그는 `~/Library/Logs/SynapseMemory/` 아래에 기록된다.
- 설치 후 운영 단계의 메모리 쓰기 action은 이 동의 범위에 포함되지 않는다.

사용자가 취소하면 다음 상태로 끝난다.

```text
status=cancelled
applied_steps=0
exit=130
```

### 단계 순서 계약

```text
start log
  → show consent
  → detect Homebrew
  → install Homebrew when missing and consented
  → detect/install Obsidian
  → detect/install Claude Code
  → detect/install apfel
  → bootstrap Synapse runtime
  → detect vault candidates
  → show GUI storage-location chooser
  → select/create vault
  → run vault setup
  → run bootstrap/install/agent loading
  → run e2e dry-run
  → show completion notification
```

M3 governance가 머지되기 전에는 setup apply step이 preview/dry-run으로 동작하거나 명시적 per-step confirmation을 받아야 한다.

### 로그 계약

Log directory:

```text
~/Library/Logs/SynapseMemory/
```

Installer log filename:

```text
installer-YYYYMMDD-HHMMSS.log
```

각 step log row는 다음 정보를 포함한다.

```text
timestamp step_id status elapsed_ms summary
```

로그에 포함하면 안 되는 것:

- Raw vault note 내용.
- Claude/Obsidian token 또는 OAuth material.
- Prompt 또는 response body.
- Private file 전체 내용.

### 롤백 계약

되돌릴 수 있는 apply step이 성공하면 installer는 다음 step으로 이동하기 전에 rollback entry를 추가해야 한다.

Rollback script path:

```text
~/.synapse/bin/rollback.sh
```

Rollback은 best-effort로 실행하고 각 시도 결과를 로그에 남긴다. 기존 사용자 vault를 삭제하면 안 된다.

## `scripts/bootstrap_runtime.sh`

분류: local runtime bootstrap helper.

### 동작 계약

Script는 다음을 만족해야 한다.

- System `python3`에 의존하지 않고 uv를 설치하거나 찾는다.
- Synapse Memory를 isolated uv-managed tool environment에 설치한다.
- `~/.synapse/bin/` 아래에 stable command shim을 만든다.
- Canonical `synapse-memory` command를 보존한다.
- 계약 테스트에서 필요성이 확인될 때만 `synapse` alias를 제공한다.
- `~/.synapse/bin/` 아래의 unrelated file을 덮어쓰지 않는다.

### 성공 기준

Bootstrap 이후 다음 명령은 `/usr/bin/python3`를 직접 resolve하지 않고 실행되어야 한다.

```bash
~/.synapse/bin/synapse-memory doctor
```

## `synapse-memory doctor`

분류: batch endpoint.

기본 동작은 read-only다. 단, 현재 doctor가 이미 소유한 안전한 directory permission normalization은 기존 동작 범위로 유지한다.

### 출력 계약

명령은 최소한 다음을 보고해야 한다.

- Synapse command path/runtime 상태.
- macOS 및 Apple Silicon 지원 여부.
- apfel 가용성.
- AI provider 가용성.
- Obsidian vault 준비 상태.
- `~/.synapse/private` 권한 상태.
- Installer-managed agent가 있을 경우 LaunchAgent 상태.

종료 코드:

| 상황 | 종료 코드 |
| --- | --- |
| 모든 required check 준비 완료 | `0` |
| 하나 이상의 required check 실패 | `1` |
| CLI argument 오류 | argparse non-zero |

## `synapse-memory doctor --fix`

분류: 명시적 local repair apply mode를 가진 batch endpoint.

### Preview 계약

Fix 적용 전 다음 형태의 preview를 출력해야 한다.

```text
Planned fixes:
1. <fix id> - <description>

Applying in 0.5s. Press Ctrl+C to cancel.
```

Countdown은 non-interactive CI test에서 test-only flag 또는 injected clock을 사용할 때만 생략할 수 있다.

### Fix 계약

명령은 whitelisted `FixAction`만 적용할 수 있다.

- `~/.synapse/private` 권한을 `0700`으로 복구.
- Installer-managed LaunchAgent reload.
- 누락된 managed command shim 재생성.
- Vault 재감지 및 installer-managed config update.

명령은 다음을 거부해야 한다.

- Unsupported hardware/OS upgrade.
- 임의의 Homebrew upgrade.
- 사용자 vault file 삭제.
- 운영 단계 메모리 쓰기.

### 로그 계약

Doctor fix log filename:

```text
doctor-fix-YYYYMMDD-HHMMSS.log
```

Log format은 installer logging contract를 따르고, 초기 diagnostic result와 각 applied fix result를 포함해야 한다.

## `/synapse-fix`

분류: slash command alias.

내부 호출:

```bash
synapse-memory doctor --fix
```

Slash command는 다음을 요약해야 한다.

- 무엇이 깨졌는지.
- 무엇을 고쳤는지.
- 무엇이 아직 수동 조치를 요구하는지.
- Repair log가 어디에 기록되었는지.
