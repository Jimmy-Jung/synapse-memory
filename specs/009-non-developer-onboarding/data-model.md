# 데이터 모델: 비개발자용 자동 온보딩

**기능**: 009-non-developer-onboarding  
**작성일**: 2026-05-12  
**작성자**: Synapse Memory Maintainers

## InstallerSession

설치 프로그램 1회 실행을 나타낸다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `session_id` | string | yes | 실행별 stable id. 로그 파일 상관관계에 사용할 수 있어야 한다. |
| `started_at` | datetime | yes | 로컬 timestamp. |
| `completed_at` | datetime | no | terminal state 이후에만 존재한다. |
| `consent` | ConsentReceipt | yes | apply step 실행 전 승인되어야 한다. |
| `selected_vault` | VaultCandidate | no | vault setup apply 전에는 필요하다. |
| `steps` | list[InstallerStepResult] | yes | 순서가 보존된 실행 로그. |
| `log_path` | path | yes | `~/Library/Logs/SynapseMemory/` 아래여야 한다. |
| `rollback_path` | path | no | reversible action이 적용된 경우 존재한다. |
| `state` | enum | yes | `planned`, `consented`, `running`, `succeeded`, `failed`, `cancelled`, `rolled_back`. |

상태 전이:

```text
planned
  → consented
  → running
  → succeeded

planned
  → cancelled

running
  → failed
  → rolled_back
```

## ConsentReceipt

사용자의 setup-stage 승인을 나타낸다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `approved` | bool | yes | Apply step은 true일 때만 가능하다. |
| `approved_at` | datetime | no | approved가 true이면 필수다. |
| `prompt_version` | string | yes | 사용자에게 보여준 문구 버전. |
| `scope` | list[string] | yes | setup action만 포함한다: vault setup, bootstrap, install, agent loading, e2e dry-run. |
| `exclusions` | list[string] | yes | 운영 단계 메모리 쓰기를 반드시 포함해야 한다. |

규칙:

- Consent는 `reflect --apply`, archive/apply, 기타 운영 단계 메모리 쓰기를 승인하지 않는다.
- Consent는 raw vault content 없이 로그에 남아야 한다.

## InstallerStep

계획된 installer action 하나를 정의한다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `id` | string | yes | `detect_homebrew` 같은 stable identifier. |
| `label` | string | yes | 한국어 사용자 표시명. |
| `kind` | enum | yes | `detect`, `install`, `configure`, `verify`, `rollback`. |
| `apply_mode` | enum | yes | `read_only`, `preview`, `apply`. |
| `requires_consent` | bool | yes | local state 변경이면 true. |
| `rollback_supported` | bool | yes | rollback action이 있을 때만 true. |

## InstallerStepResult

Installer step 하나의 실행 결과다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `step_id` | string | yes | InstallerStep.id와 일치해야 한다. |
| `status` | enum | yes | `pending`, `skipped`, `success`, `failed`, `rolled_back`. |
| `started_at` | datetime | no | 실행된 step에는 필수다. |
| `elapsed_ms` | integer | no | 0 이상. |
| `summary` | string | yes | raw vault content를 포함하면 안 된다. |
| `remediation` | string | no | 자동 복구 불가 실패에는 필요하다. |

## VaultCandidate

감지된 Obsidian 호환 vault directory다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `path` | path | yes | 존재하거나 default candidate의 경우 생성 가능해야 한다. |
| `source` | enum | yes | `icloud_obsidian`, `documents_obsidian`, `conventional`, `existing_config`, `created_default`. |
| `display_name` | string | yes | GUI 목록에 안전하게 표시 가능해야 한다. |
| `has_obsidian_dir` | bool | yes | `.obsidian/` 존재 여부. |
| `confidence` | integer | yes | 0-100. |
| `needs_creation` | bool | yes | default vault proposal일 때만 true. |
| `is_recommended` | bool | yes | installer가 추천하는 생성 위치이면 true. |

정렬 순서:

```text
existing_config valid
  → iCloud Obsidian with .obsidian
  → Documents vault with .obsidian
  → conventional path with .obsidian
  → iCloud default creation proposal
  → local Documents creation proposal
```

## DiagnosticResult

Health check 하나의 machine-readable 결과다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `check_id` | string | yes | Stable identifier. |
| `status` | enum | yes | `ok`, `warn`, `fail`, `unknown`. |
| `message` | string | yes | 사용자에게 보여줄 한국어 메시지. |
| `details` | object | no | secret 또는 raw content를 포함하면 안 된다. |
| `fixable` | bool | yes | FixAction이 있을 때만 true. |
| `fix_action_id` | string | no | fixable이면 필수. |

## FixAction

`doctor --fix`가 사용할 whitelisted repair action이다.

| 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `id` | string | yes | Stable identifier. |
| `target_check_id` | string | yes | DiagnosticResult.check_id. |
| `description` | string | yes | Dry-run preview에 표시된다. |
| `risk` | enum | yes | `low`, `medium`; MVP에는 high-risk auto-fix가 없다. |
| `requires_installer_consent` | bool | yes | installer-owned setup repair이면 true. |
| `apply` | callable/command contract | yes | idempotent해야 한다. |
| `rollback` | callable/command contract | no | 실용적으로 되돌릴 수 있는 상태 변경에는 필요하다. |

첫 릴리스 허용 action:

- `~/.synapse/private` 권한을 `0700`으로 복구.
- Installer-managed LaunchAgent plist reload.
- 누락된 managed command shim 재생성.
- Vault 재감지 및 installer-managed config update.

금지 action:

- 임의의 vault note 편집.
- 사용자 데이터 삭제.
- Raw vault content를 외부 서비스로 전송.
- 지원하지 않는 OS upgrade 설치.
