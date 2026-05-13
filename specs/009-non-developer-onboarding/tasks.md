# 작업 목록: 비개발자용 자동 온보딩

**입력**: `specs/009-non-developer-onboarding/` 설계 문서  
**전제**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/installer-contracts.md](./contracts/installer-contracts.md), [quickstart.md](./quickstart.md)

## Phase 1: Setup

- [X] T001 `src/synapse_memory/installer/` 패키지 구조를 생성한다.
- [X] T002 `installer/`와 `scripts/` 디렉터리를 생성한다.

## Phase 2: Foundation

- [X] T003 [P] Installer 상태 모델 실패 테스트를 `tests/test_installer_state.py`에 작성한다.
- [X] T004 [P] Vault 감지 실패 테스트를 `tests/test_vault_detector.py`에 작성한다.
- [X] T005 [P] Runtime bootstrap 계약 실패 테스트를 `tests/test_runtime_bootstrap_contract.py`에 작성한다.
- [X] T006 [P] Doctor fix 실패 테스트를 `tests/test_doctor_fix.py`에 작성한다.
- [X] T007 [P] CLI doctor --fix 실패 테스트를 `tests/test_cli_doctor_fix.py`에 작성한다.

## Phase 3: 사용자 스토리 1 - 더블클릭 설치로 기본 설정 완료 (P1)

**목표**: 비개발자가 `.command` 파일을 실행해 안전한 setup preview와 로그를 얻는다.

**독립 테스트**: `.command` dry-run 실행 시 로그가 생성되고 apply 전 preview 단계로 끝난다.

- [X] T008 [US1] Installer 상태 모델을 `src/synapse_memory/installer/state.py`에 구현한다.
- [X] T009 [US1] Installer 로그 helper를 `src/synapse_memory/installer/logging.py`에 구현한다.
- [X] T010 [US1] Runtime bootstrap helper 계약을 `src/synapse_memory/installer/runtime.py`에 구현한다.
- [X] T011 [US1] Runtime bootstrap shell script를 `scripts/bootstrap_runtime.sh`에 구현한다.
- [X] T012 [US1] Double-click installer skeleton을 `installer/SynapseMemory-Installer.command`에 구현한다.

## Phase 4: 사용자 스토리 2 - Obsidian Vault 자동 감지 또는 생성 (P2)

**목표**: 기존 vault를 찾고, 새 저장소를 만들 경우 iCloud 추천 위치와 local fallback을 제공한다.

**독립 테스트**: iCloud, Documents, 기존 config, no-vault fixture에서 후보 ordering과 iCloud 추천 생성 위치가 검증된다.

- [X] T013 [US2] Vault 후보 모델과 감지 로직을 `src/synapse_memory/vault_detector.py`에 구현한다.
- [X] T014 [US2] Installer skeleton에 vault 감지 dry-run 출력을 연결한다.
- [X] T014a [US2] Installer GUI에서 기존 vault, 추천 iCloud 위치, local fallback, 직접 선택을 고를 수 있게 한다.

## Phase 5: 사용자 스토리 3 - 한 번의 복구 명령으로 깨진 설치 복구 (P3)

**목표**: `synapse-memory doctor --fix`가 whitelisted repair만 preview/apply한다.

**독립 테스트**: 권한 drift, LaunchAgent unloaded, command shim 누락, vault missing 상태가 whitelisted action으로 매핑된다.

- [X] T015 [US3] Structured diagnostic과 fix action을 `src/synapse_memory/doctor.py`에 구현한다.
- [X] T016 [US3] `synapse-memory doctor --fix` CLI parser와 command flow를 `src/synapse_memory/cli.py`에 연결한다.
- [X] T017 [US3] `/synapse-fix` alias를 `commands/synapse-fix.md`에 추가하고 `commands/synapse-doctor.md`를 갱신한다.

## Phase 6: 사용자 스토리 4 - 설치 동의와 복구 이력 감사 (P4)

**목표**: Installer consent policy와 public docs를 한글로 일관되게 맞춘다.

- [X] T018 [US4] Constitution v1.1.0에 Installation Consent Scoping을 `.specify/memory/constitution.md`에 반영한다.
- [X] T019 [US4] `skills/synapse-memory/SKILL.md`에 Interactive mode와 Installer mode를 문서화한다.
- [X] T020 [US4] `README.md`, `docs/usage.md`, `docs/commands.md`에 비개발자/개발자 설치 경로와 `doctor --fix`를 반영한다.

## Phase 7: 검증

- [X] T021 관련 테스트 파일을 pytest로 실행한다.
- [X] T022 전체 테스트를 가능한 범위에서 실행한다.
- [X] T023 `git diff --check`와 문서 placeholder 검색을 실행한다.

## 의존 순서

1. T001-T002
2. T003-T007
3. T008-T012
4. T013-T014
5. T015-T017
6. T018-T020
7. T021-T023
