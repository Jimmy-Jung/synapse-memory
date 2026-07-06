# 기능 명세: 비개발자용 자동 온보딩

**기능 브랜치**: `009-non-developer-onboarding`  
**작성일**: 2026-05-12  
**작성자**: Synapse Memory Maintainers  
**상태**: 초안  
**입력**: "비개발자가 GUI 더블클릭 한 번으로 Synapse Memory를 작동 상태로 만든다"

## 사용자 시나리오 및 테스트 *(필수)*

### 사용자 스토리 1 - 더블클릭 설치로 기본 설정 완료 (우선순위: P1)

비개발자는 README를 길게 읽거나 터미널 명령을 직접 조합하지 않고, Finder에서 설치 파일을 더블클릭한 뒤 한 번 동의해서 Synapse Memory를 사용 가능한 상태로 만든다.

**우선순위 이유**: 이 기능의 핵심 가치다. 사용자가 첫 설치에서 실패하면 이후 memory, daily, doctor 기능은 체감 가치가 없다.

**독립 테스트**: 새 macOS 사용자 계정에서 설치 파일을 더블클릭하고 안내를 따라 완료했을 때, Synapse Memory 상태 확인 명령이 vault 준비 완료 상태를 보여주면 MVP 가치가 있다.

**인수 시나리오**:

1. **주어진 상황** Synapse Memory가 설치되지 않은 새 macOS Apple Silicon 계정, **동작** 사용자가 설치 파일을 더블클릭하고 설치 동의 다이얼로그에서 승인한다, **결과** Synapse Memory CLI, vault 연결, 기본 자동화 준비 상태가 5분 안에 완료된다.
2. **주어진 상황** 필수 앱 일부가 이미 설치된 macOS 계정, **동작** 사용자가 설치 파일을 실행한다, **결과** 설치 프로그램은 기존 설치를 재사용하고 중복 설치 없이 다음 단계로 진행한다.
3. **주어진 상황** 설치 중 복구 가능한 단계가 실패한다, **동작** 설치 프로그램이 실패를 감지한다, **결과** 사용자는 실패 원인, 로그 파일 경로, 자동 롤백 또는 재시도 안내를 받는다.

---

### 사용자 스토리 2 - Obsidian Vault 자동 감지 또는 생성 (우선순위: P2)

비개발자는 Obsidian vault 경로를 몰라도 설치 프로그램이 후보 vault를 찾아주고, GUI 선택창에서 기존 vault 또는 새 저장소 위치를 고른다. iCloud Obsidian 폴더가 있으면 새 저장소 추천 위치는 iCloud의 `SynapseVault`다.

**우선순위 이유**: Synapse Memory의 진실원본은 vault다. vault 선택이 막히면 설치는 성공해도 제품이 동작하지 않는다.

**독립 테스트**: iCloud Obsidian vault, `~/Documents` vault, vault 없음 세 환경에서 설치 프로그램의 선택/생성 결과를 각각 검증할 수 있다.

**인수 시나리오**:

1. **주어진 상황** iCloud Obsidian vault가 하나 존재한다, **동작** 설치 프로그램이 vault 감지를 실행한다, **결과** 해당 vault를 자동 선택하고 설정에 반영한다.
2. **주어진 상황** 여러 vault 후보가 존재한다, **동작** 설치 프로그램이 후보 목록을 표시한다, **결과** 사용자가 GUI 목록에서 하나를 선택하고 선택 결과가 설정에 반영된다.
3. **주어진 상황** iCloud Obsidian container가 있고 vault 후보가 없다, **동작** 설치 프로그램이 vault setup을 진행한다, **결과** `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SynapseVault`가 추천 생성 위치로 표시된다.
4. **주어진 상황** iCloud Obsidian container가 없다, **동작** 설치 프로그램이 vault setup을 진행한다, **결과** `~/Documents/SynapseVault`가 fallback 생성 위치로 표시된다.

---

### 사용자 스토리 3 - 한 번의 복구 명령으로 깨진 설치 복구 (우선순위: P3)

설치 후 자동화나 vault 경로가 깨졌을 때 비개발자는 채팅창이나 문서에 안내된 복구 명령 한 번으로 진단과 안전한 복구를 실행한다.

**우선순위 이유**: 설치 성공 이후에도 LaunchAgent, PATH, vault 이동 같은 환경 드리프트가 발생한다. 비개발자에게는 복구 경험이 초기 설치만큼 중요하다.

**독립 테스트**: LaunchAgent를 수동으로 unload하거나 vault 경로를 이동한 뒤 복구 명령을 실행해 정상 상태로 돌아오는지 검증한다.

**인수 시나리오**:

1. **주어진 상황** Synapse Memory LaunchAgent가 unload된 상태, **동작** 사용자가 복구 명령을 실행한다, **결과** 시스템은 문제를 진단하고 허용된 복구 액션으로 LaunchAgent를 다시 로드한다.
2. **주어진 상황** vault 경로가 변경된 상태, **동작** 사용자가 복구 명령을 실행한다, **결과** 시스템은 vault를 다시 감지하고 사용자 확인 범위 안에서 설정을 갱신한다.
3. **주어진 상황** Python 런타임 자체가 손상된 상태, **동작** 사용자가 복구 명령을 실행한다, **결과** 시스템은 자동 복구 대신 설치 프로그램 재실행 안내를 표시한다.

---

### 사용자 스토리 4 - 설치 동의와 복구 이력 감사 (우선순위: P4)

메인테이너는 설치 프로그램이 어떤 작업을 수행했는지 단일 로그에서 추적하고, 설치 단계 동의 범위가 프로젝트 정책과 충돌하지 않는지 확인할 수 있다.

**우선순위 이유**: 자동 설치는 사용자의 로컬 환경을 변경한다. 설치 UX를 단순화해도 감사 이력과 거버넌스가 없으면 신뢰를 잃는다.

**독립 테스트**: 설치 및 복구 로그를 읽어 동의 시각, 실행 단계, 성공/실패, 롤백 여부가 남는지 확인한다.

**인수 시나리오**:

1. **주어진 상황** 설치 프로그램이 여러 적용 단계를 실행한다, **동작** 설치가 완료된다, **결과** 모든 적용 단계와 결과가 하나의 installer log에 남는다.
2. **주어진 상황** 프로젝트 헌법이 설치 동의 범위를 정의한다, **동작** 설치 프로그램이 apply 단계를 실행한다, **결과** 설치 단계 동의와 운영 단계 메모리 쓰기 승인이 명확히 분리된다.

### 엣지 케이스

- Homebrew가 없거나 설치 중 사용자 암호 입력이 필요한 경우.
- Obsidian 또는 Claude Code가 이미 설치되어 있으나 Homebrew 관리 대상이 아닌 경우.
- iCloud vault가 Finder에는 보이지만 아직 동기화 중이라 `.obsidian/`이 늦게 나타나는 경우.
- Gatekeeper가 `.command` 실행을 막는 경우.
- 사용자가 설치 동의 다이얼로그에서 취소하는 경우.
- 네트워크가 없어 `uv`, Homebrew formula, cask 다운로드가 불가능한 경우.
- 기존 `~/.synapse`가 손상되었거나 권한이 `0700`이 아닌 경우.
- 여러 Synapse Memory 버전이 PATH에 동시에 존재하는 경우.

## 요구사항 *(필수)*

### 기능 요구사항

- **FR-001**: 시스템은 비개발자 온보딩을 위한 macOS 더블클릭 설치 진입점을 제공해야 한다.
- **FR-002**: 시스템은 사용자의 머신 상태를 변경하기 전에 GUI 동의 프롬프트를 표시해야 한다.
- **FR-003**: 시스템은 각 설치 단계와 실패를 감사할 수 있도록 `~/Library/Logs/SynapseMemory/` 아래에 설치 로그를 기록해야 한다.
- **FR-004**: 시스템은 필수 도구를 설치하거나 수정하기 전에 기존 설치 여부를 감지해야 한다.
- **FR-005**: 시스템은 지원 macOS 플랫폼에서 Synapse Memory가 동작하는 데 필요한 앱과 CLI 의존성을 설치하거나 설치 안내를 제공해야 한다.
- **FR-006**: 시스템은 사전 설치된 system `python3`에 의존하지 않는 Synapse Memory 명령 경로를 부트스트랩해야 한다.
- **FR-007**: 시스템은 일반적인 local/iCloud 위치에서 Obsidian vault 후보를 감지해야 한다.
- **FR-008**: 시스템은 설치 GUI에서 기존 vault, 추천 새 vault 위치, local fallback, 직접 선택을 고를 수 있는 선택 흐름을 제공해야 한다.
- **FR-009**: 시스템은 iCloud Obsidian container가 있으면 새 vault 추천 위치를 iCloud로 제안하고, 없으면 local Documents로 fallback해야 한다.
- **FR-010**: 시스템은 vault, bootstrap, install, agent loading setup 단계를 감사 및 재시도 가능한 순서로 실행해야 한다.
- **FR-011**: 시스템은 설치 프로그램이 적용 작업을 수행하기 전에 계획된 apply 작업의 dry-run 또는 preview를 제공해야 한다.
- **FR-012**: 시스템은 설치 단계가 변경을 수행한 뒤 실패하면 rollback 또는 안전한 복구 안내를 제공해야 한다.
- **FR-013**: 시스템은 알려진 깨진 상태를 진단하고 whitelisted fix만 적용하는 repair mode를 제공해야 한다.
- **FR-014**: 시스템은 운영 단계의 메모리 쓰기 작업을 1회성 설치 동의 범위 밖에 유지해야 한다.
- **FR-015**: 시스템은 비개발자용 설치 경로와 개발자용 설치 경로를 문서에서 분리해 설명해야 한다.
- **FR-016**: 시스템은 실제 Obsidian vault 내용, 사용자 secret, Claude Code 로그인 상태, 실제 local LLM 실행 없이도 CI에서 테스트 가능해야 한다.

### 핵심 엔티티

- **Installer Session**: 설치 프로그램 1회 실행을 나타낸다. 동의 결과, 선택된 vault, 단계 결과, 로그 경로, rollback 경로를 포함한다.
- **Installer Step**: 의존성 확인, runtime bootstrap, vault setup, plugin install 같은 개별 설치 작업을 나타낸다.
- **Vault Candidate**: 감지된 Obsidian 호환 디렉터리다. 출처, 신뢰도, 표시 이름을 가진다.
- **Diagnostic Result**: 의존성 또는 subsystem 하나에 대한 machine-readable health check 결과다.
- **Fix Action**: preview, apply, log가 가능한 whitelisted repair 작업이다.
- **Consent Scope**: 1회성 설치 apply 작업과 이후 운영 단계 메모리 쓰기를 구분하는 동의 범위다.

## 성공 기준 *(필수)*

### 측정 가능한 결과

- **SC-001**: 지원되는 새 macOS 사용자 계정에서 비개발자가 설치 파일 실행 후 5분 이내에 설치를 완료할 수 있다.
- **SC-002**: 설치 성공 후 status check가 사용자의 파일시스템 경로 입력 없이 `vault_ready: true` 또는 동등한 ready 상태를 표시한다.
- **SC-003**: 설치 프로그램은 완료, skip, 실패, rollback된 단계 100%에 대해 단일 로그 파일을 생성한다.
- **SC-004**: PATH에서 `python3`가 없는 테스트 환경에서도 설치된 Synapse Memory 명령이 status 또는 doctor check를 실행한다.
- **SC-005**: Vault 감지는 단일 기존 vault, 여러 후보 vault, 기존 vault 없음의 세 주요 시나리오를 올바르게 처리한다.
- **SC-006**: 복구 명령은 테스트로 커버된 whitelisted broken state를 복구하고, whitelist 밖의 복구는 명확한 안내와 함께 거부한다.
- **SC-007**: 프로젝트 문서는 비개발자 setup 경로와 개발자 setup 경로를 constitution consent policy와 모순 없이 설명한다.

## 가정

- 지원 플랫폼은 현재 apfel 및 constitution platform floor와 동일하게 Apple Silicon macOS 26 Tahoe 이상으로 유지한다.
- Homebrew는 Obsidian, Claude Code, apfel을 formula 또는 cask로 설치할 수 있으므로 첫 릴리스 온보딩의 기본 package manager로 사용한다.
- 코드사인 및 notarized `.pkg` 배포는 이 feature의 MVP 범위 밖이며 후속 release track으로 둔다.
- 첫 설치 시 의존성 다운로드를 위해 인터넷 연결이 필요할 수 있다.
- 단일 초기 installer consent가 setup apply 단계를 포괄하려면 M3에서 constitution 개정이 먼저 완료되어야 한다.
- Daily memory reflection, archive, 기타 운영 단계 메모리 쓰기 명령은 기존처럼 명시적 개별 승인이 필요하다.
