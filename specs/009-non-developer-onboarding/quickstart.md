# 빠른 시작: 비개발자용 자동 온보딩

**기능**: 009-non-developer-onboarding  
**작성일**: 2026-05-12  
**작성자**: Synapse Memory Maintainers

## 목표

지원되는 새 Mac 계정에서 비개발자가 5분 이내에 Synapse Memory를 사용할 수 있는지 검증한다.

## 시나리오 A - 새 macOS 계정

전제 조건:

- Apple Silicon Mac.
- macOS 26 Tahoe 이상.
- Apple Intelligence 활성화.
- 네트워크 사용 가능.
- `python3`가 설치되어 있거나 PATH에 있다고 가정하지 않는다.

단계:

1. Synapse Memory release zip을 다운로드한다.
2. 압축을 푼다.
3. `SynapseMemory-Installer.command`를 더블클릭한다.
4. Setup consent dialog를 승인한다.
5. 완료 notification을 기다린다.
6. Installer가 표시한 status command를 실행한다.

기대 결과:

```text
vault_ready: true
runtime_ready: true
doctor_ready: true
```

Installer log가 존재한다.

```text
~/Library/Logs/SynapseMemory/installer-YYYYMMDD-HHMMSS.log
```

## 시나리오 B - 기존 Obsidian 사용자

전제 조건:

- Obsidian이 이미 설치되어 있다.
- iCloud Obsidian 또는 `~/Documents` 아래에 하나 이상의 기존 vault가 있다.

단계:

1. `SynapseMemory-Installer.command`를 더블클릭한다.
2. Setup을 승인한다.
3. 여러 vault 또는 새 저장소 위치 후보가 표시되면 의도한 vault를 선택한다. 새로 만들 경우 추천값은 iCloud Obsidian 폴더의 `SynapseVault`다.
4. Setup을 완료한다.

기대 결과:

- 선택된 vault path가 완료 summary에 표시된다.
- Synapse Memory setup file은 선택한 vault에만 생성된다.
- 관련 없는 vault는 수정되지 않는다.

## 시나리오 C - 기존 Vault 없음

전제 조건:

- Obsidian 설치 여부와 무관하다.
- 일반 검색 경로 아래에 `.obsidian/` directory가 없다.

단계:

1. Installer를 실행한다.
2. Setup을 승인한다.
3. 기본 vault 생성 경로를 수락한다.

기대 결과:

```text
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SynapseVault
```

위 iCloud Obsidian container가 존재하면 해당 경로가 추천된다. iCloud container가 없으면 `~/Documents/SynapseVault`가 fallback으로 추천된다. 선택한 경로는 Obsidian에서 열 수 있거나 열 준비가 된다.

## 시나리오 D - 깨진 LaunchAgent 복구

전제 조건:

- Synapse Memory가 installer로 설치되어 있다.
- Installer-managed LaunchAgent가 존재한다.
- LaunchAgent가 수동으로 unload된 상태다.

단계:

1. 다음 명령을 실행한다.

   ```bash
   synapse-memory doctor --fix
   ```

2. Planned fixes를 확인한다.
3. Ctrl+C를 누르지 않는다.
4. 다음 명령을 다시 실행한다.

   ```bash
   synapse-memory doctor
   ```

기대 결과:

- `doctor --fix`가 installer-managed LaunchAgent를 reload한다.
- `doctor`가 LaunchAgent ready 상태를 보고한다.
- Repair log가 `~/Library/Logs/SynapseMemory/` 아래에 존재한다.

## 시나리오 E - 지원하지 않는 머신

전제 조건:

- Intel Mac 또는 macOS 26 미만.

단계:

1. Installer를 실행한다.

기대 결과:

- Installer는 unsupported setup을 적용하기 전에 종료한다.
- Apple Silicon 및 macOS 26+ 요구사항을 설명한다.
- Log file에 unsupported platform status가 기록된다.
- 이미 명시적으로 preview 및 승인된 경우가 아니라면 vault 또는 runtime mutation은 일어나지 않는다.
