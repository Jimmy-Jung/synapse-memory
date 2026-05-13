# 구현 계획: 비개발자용 자동 온보딩

**브랜치**: `009-non-developer-onboarding` | **작성일**: 2026-05-12 | **명세**: [spec.md](./spec.md)  
**작성자**: Synapse Memory Maintainers  
**입력**: `specs/009-non-developer-onboarding/spec.md` 기능 명세

## 요약

지원 macOS 사용자가 설치 파일을 더블클릭하고 한 번의 setup 동의를 승인하면 Synapse Memory가 Obsidian vault와 연결된 작동 상태가 되도록 비개발자용 온보딩 경로를 추가한다. 구현은 독립적으로 리뷰 가능한 4개 마일스톤으로 나눈다: installer UX skeleton, runtime 의존성 번들링, 운영 복구 자동화, governance 및 문서 정합성.

사용자 요청의 PR 권장 순서는 **M2 → M1 → M4 → M3**이다. 다만 실제 기술 완성 순서는 **M1 → M2 full e2e → M3 policy gate → M4 final hardening**에 가깝다. 따라서 M2는 먼저 안전한 dry-run/preview installer skeleton으로 시작하고, M1과 M3가 닫힌 뒤 full apply mode를 완성한다.

## 기술 맥락

**언어/버전**: Python 3.11+ package, zsh installer, AppleScript GUI prompt  
**주요 의존성**: 기존 `synapse_memory` package, Homebrew, uv, apfel, Obsidian, Claude Code CLI  
**저장소/파일 상태**: `~/.synapse/private/`, `~/.synapse/bin/`, `~/Library/Logs/SynapseMemory/`, 선택된 Obsidian vault  
**테스트**: Python module은 pytest, installer script는 가능한 범위에서 shell validation, 외부 도구 부재 상황은 mock 기반 CI, 최종 검증은 새 macOS 계정 smoke test  
**대상 플랫폼**: Apple Silicon macOS 26 Tahoe 이상  
**프로젝트 유형**: Python CLI/library + macOS installer script  
**성능 목표**: 새 지원 계정에서 installer 실행 후 5분 이내 온보딩 완료, 네트워크 설치 시간을 제외한 status/doctor check는 5초 미만  
**제약**: local-first privacy, 로그에 raw vault data 금지, 설치된 명령 경로는 system `python3`에 의존 금지, silent privilege escalation 금지, installer consent는 audit 가능해야 함  
**범위**: 단일 사용자 local workstation, 선택된 vault 1개, 첫 릴리스는 `.command` installer와 CLI repair path

## 현재 코드 기준 보정

- 현재 `pyproject.toml`에는 이미 `synapse-memory = "synapse_memory.cli:main"` console script가 있다.
- 현재 브랜치에는 `scripts/synapse.py`가 없으므로 M1에서 해당 파일 이동을 계획하면 안 된다.
- M1은 필요할 때만 짧은 alias인 `synapse`를 추가한다. 기존 `synapse-memory`는 반드시 backward compatible하게 유지한다.
- 기존 slash command는 `synapse-memory`를 호출하므로 command markdown 변경은 compatibility 관점에서 최소화한다.

## 헌법 검토

*검토 기준: Phase 0 조사 전 통과해야 하며, Phase 1 설계 후 다시 확인한다.*

| 원칙 | 검토 결과 | 근거 / 완화 |
| --- | --- | --- |
| I. Local-First & Privacy by Default | 통과 | Installer와 repair는 local machine 상태만 변경한다. 로그에는 raw vault 내용과 secret을 남기지 않는다. |
| II. Two-Pass Redaction | 통과 | 새 외부 text boundary를 만들지 않는다. 기존 redaction stack을 설치/진단한다. |
| III. Test-First Discipline | 통과 | 각 마일스톤은 구현 전 실패 테스트를 포함한다. 외부 도구는 mock 기반 CI로 검증한다. |
| IV. Conversation-Context-Aware Endpoints | 통과 | `doctor`와 repair는 batch endpoint다. installer는 conversation endpoint가 아니다. |
| V. Reproducible Daily Pipeline & Observability | 조건부 통과 | `doctor --fix`가 observability와 repair를 확장한다. `daily` idempotence를 깨면 안 된다. |

**거버넌스 메모**: Full installer apply mode는 M3의 Installation Consent Scoping이 필요하다. 해당 개정 전까지 M2는 apply 단계를 preview/dry-run 또는 명시적 per-step 확인 뒤에만 실행해야 한다.

## 프로젝트 구조

### 이 feature의 문서

```text
specs/009-non-developer-onboarding/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── installer-contracts.md
└── checklists/
    └── requirements.md
```

### 예상 source code 변경

```text
installer/
└── SynapseMemory-Installer.command       # M2 macOS double-click installer

scripts/
└── bootstrap_runtime.sh                  # M1 uv/runtime bootstrap helper

src/synapse_memory/
├── cli.py                                # doctor --fix, status/bootstrap/install alias 연결
├── installer/
│   ├── __init__.py
│   ├── logging.py                        # installer/doctor log helper
│   ├── runtime.py                        # uv/runtime check
│   ├── state.py                          # installer state machine
│   └── rollback.py                       # rollback manifest 및 실행
├── vault_detector.py                     # M2 Obsidian vault 감지
└── doctor.py                             # M4 diagnostic-to-fix mapping

commands/
├── synapse-doctor.md                     # --fix 설명 추가
└── synapse-fix.md                        # repair alias

tests/
├── test_installer_state.py
├── test_vault_detector.py
├── test_doctor_fix.py
├── test_runtime_bootstrap_contract.py
└── test_cli_doctor_fix.py
```

**구조 결정**: `.command` script는 얇게 유지하고 installer 상태/로그/rollback은 `src/synapse_memory/installer/`에 둔다. Vault discovery는 installer와 doctor repair가 함께 쓰므로 top-level domain module인 `src/synapse_memory/vault_detector.py`로 둔다. Repair logic은 CLI parsing과 분리해 `doctor.py`에 둔다.

## Phase 0 산출물

[research.md](./research.md)를 참조한다.

## Phase 1 산출물

- [data-model.md](./data-model.md)
- [contracts/installer-contracts.md](./contracts/installer-contracts.md)
- [quickstart.md](./quickstart.md)

## 마일스톤 계획

### M2 - 원클릭 인스톨러 Skeleton

**목표**: Runtime bundling과 governance 변경이 끝나기 전에도 안전하게 리뷰 가능한 더블클릭 installer surface를 제공한다.

**범위**:

- `installer/SynapseMemory-Installer.command` 추가.
- AppleScript 동의 prompt 및 취소 경로 구현.
- `~/Library/Logs/SynapseMemory/installer-YYYYMMDD-HHMMSS.log` 생성.
- Homebrew, Obsidian, Claude Code, apfel, 기존 Synapse command, vault 후보 감지.
- `src/synapse_memory/vault_detector.py` 추가.
- GUI 저장소 위치 선택 지원: 기존 vault, 추천 iCloud `SynapseVault`, local Documents fallback, 직접 선택.
- iCloud Obsidian container가 있으면 새 vault 추천 위치를 iCloud로 우선 제안하고, 없으면 `~/Documents/SynapseVault`로 fallback.
- M1/M3 gate가 만족되기 전까지 setup step은 dry-run/preview mode로 제한.

**테스트**:

- Vault candidate scoring 및 다중 후보 ordering 실패 테스트.
- Installer state transition 및 log redaction 실패 테스트.
- `.command`가 zsh에서 시작되고 dry-run mode에서 로그를 쓰는 shell smoke test.

**머지 가치**: 비개발자가 guided preflight를 실행하고 setup이 무엇을 할지 확인할 수 있다.

### M1 - Runtime 및 PATH 독립성

**목표**: 설치된 사용 경로에서 system `python3`와 불안정한 PATH 가정 제거.

**범위**:

- `scripts/bootstrap_runtime.sh` 추가.
- uv standalone installer 또는 관리되는 uv binary path로 bootstrap.
- 기존 `synapse-memory` console script 유지.
- Installer UX에 필요하다는 contract test가 있으면 `synapse` alias 추가.
- uv tool semantics로 project를 isolated tool environment에 설치.
- `~/.synapse/bin` 아래 stable entrypoint를 생성하고 shell profile 수정에 의존하지 않게 한다.
- apfel은 plugin zip에 동봉하지 않고 Homebrew formula 설치를 기본 전략으로 삼는다.

**테스트**:

- 생성된 command shim이 `/usr/bin/python3`를 직접 실행하지 않는 contract test.
- uv 이미 설치됨, uv 없음, network failure path에 대한 mocked bootstrap test.
- PATH에서 `python3`를 제거한 상태에서도 `synapse-memory doctor` 또는 `synapse status`가 managed shim으로 실행되는 CI/scripted check.

**머지 가치**: Python이 사전 설치되지 않았거나 PATH에 없어도 installer가 안정적인 Synapse command를 만들 수 있다.

### M4 - `doctor --fix`

**목표**: 비개발자가 흔한 설치 drift를 한 번의 명시적 fix 명령으로 복구할 수 있게 한다.

**범위**:

- Structured diagnostics 및 whitelisted fixes를 위한 `src/synapse_memory/doctor.py` 추가.
- `synapse-memory doctor --fix` 및 `/synapse-fix` 추가.
- 기본 `doctor`는 read-only 유지.
- Fix 적용 전 dry-run preview와 짧은 Ctrl+C grace period 제공.
- `~/Library/Logs/SynapseMemory/doctor-fix-YYYYMMDD-HHMMSS.log` 기록.
- Installer-owned setup repair에는 installer consent를 재사용하되, 운영 메모리 쓰기는 거부.

**테스트**:

- LaunchAgent unloaded -> load action 실패 테스트.
- Vault missing -> detect/select/setup action 실패 테스트.
- Damaged runtime -> unsafe mutation 대신 installer rerun guidance 테스트.
- `doctor` read-only와 `doctor --fix` apply mode CLI 테스트.

**머지 가치**: 사용자가 내부 문서를 읽지 않고도 일반적인 설치 깨짐을 복구할 수 있다.

### M3 - Governance 및 문서 개정

**목표**: Installer consent policy를 명시하고 공개 문서의 정합성을 맞춘다.

**범위**:

- `.specify/memory/constitution.md`를 v1.0.0에서 v1.1.0으로 개정.
- Installation Consent Scoping 추가:
  - 초기 installer consent는 `vault-setup`, `bootstrap`, `install`, agent loading setup action을 포괄한다.
  - `reflect --apply`, archive/apply 같은 운영 메모리 쓰기는 계속 개별 승인 대상이다.
  - Installer는 계획된 apply 작업을 preview하고 audit log를 남겨야 한다.
- `skills/synapse-memory/SKILL.md`에 Interactive mode와 Installer mode 분리.
- 필요 시 `README.md`, `docs/getting-started.md`, `docs/usage.md`, `docs/commands.md`, `CLAUDE.md` 동기화.

**테스트**:

- Installer/developer setup path 문서 정합성 검사.
- 어떤 문서도 운영 메모리 쓰기가 installer consent에 포함된다고 말하지 않는지 checklist review.

**머지 가치**: Full installer apply behavior가 governance와 충돌하지 않고 리뷰 가능해진다.

## 의존 그래프

```text
M2 skeleton ──┐
              ├─> M2 full e2e
M1 runtime ───┘

M1 runtime ──> M4 doctor --fix
M2 skeleton ─> M4 doctor --fix

M3 governance must land before M2 full apply mode is released.
```

## 리스크 목록

| 리스크 | 영향 | 완화 |
| --- | --- | --- |
| apfel packaging/redistribution 불확실성 | 동봉 전략을 택하면 M1 지연 | Homebrew formula 설치를 기본으로 삼고 MIT/license/platform 요구사항을 research에 기록. |
| Gatekeeper가 `.command` 실행 차단 | 사용자 마찰 | MVP 문서에 우회 안내를 포함하고 notarized `.pkg`는 별도 track으로 분리. |
| Homebrew 설치가 암호 입력 또는 실패를 요구 | Installer 중단 | 명확한 UI/log message 제공, 단계 상태를 rerunnable하게 유지. |
| iCloud vault 감지와 sync timing 충돌 | 잘못된 vault 또는 누락 | 여러 heuristic, GUI 선택, retry 지원. |
| 단일 consent가 현재 constitution과 충돌 | Governance violation | M3 v1.1.0 전까지 full apply mode release 금지. |
| 로그에 민감 정보 노출 | Privacy issue | 로그에는 path/status만 기록하고 raw file content와 prompt/response body 금지. |

## 헌법 검토 (설계 후 재확인)

| 원칙 | 결과 |
| --- | --- |
| I. Local-First & Privacy by Default | 통과. Installer와 repair는 local에 머물며 log contract가 raw vault content를 금지한다. |
| II. Two-Pass Redaction | 통과. 새 외부 text emission path를 만들지 않는다. |
| III. Test-First Discipline | 통과. 마일스톤별 RED test를 구현 전에 정의했다. |
| IV. Conversation-Context-Aware Endpoints | 통과. Repair는 batch이고 unattended-safe해야 하며 새 interactive LLM endpoint를 만들지 않는다. |
| V. Reproducible Daily Pipeline & Observability | 통과. `doctor --fix`는 observability를 강화하고 daily stage ordering을 변경하지 않는다. |

**최종 검토 결과**: 통과. 단, full installer apply mode는 M3 governance dependency를 가진다.

## 복잡도 추적

이 계획에서는 승인된 constitution violation이 없다.
