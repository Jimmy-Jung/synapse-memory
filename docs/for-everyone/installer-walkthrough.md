# 설치 화면 가이드 (비개발자용)

> 더블클릭 설치 프로그램을 처음 실행할 때 어떤 화면이 나오고
> 무엇을 클릭해야 하는지 단계별로 설명합니다.

## 어떤 상태에서 어디부터 보면 되나

| 상태 | 가는 곳 |
|---|---|
| "처음 다운로드부터 시작" | [§1 설치 zip 다운로드](#1단계--설치-zip-다운로드) |
| ".command 파일을 어디서 찾나" | [§2 .command 실행](#2단계--command-파일-실행) |
| "macOS 보안 경고가 떴다 / '열기' 버튼이 안 보인다" | [§ macOS 보안 경고](#macos-보안-경고) |
| "GUI 안내가 뜨면 뭘 클릭해야 하나" | [§3 설치 프로그램 진행](#3단계--설치-프로그램-진행) |
| "vault 위치를 어디로 골라야 하나" | [§3-4 Obsidian 저장소 위치 선택](#3-4-obsidian-저장소vault-위치-선택) |
| "설치 후 첫 명령" | [§4 첫 질문](#4단계--claude-code에서-첫-질문) |
| "뭐가 어디에 설치됐나" | [§ 무엇이 어디에 설치되나요?](#무엇이-어디에-설치되나요) |
| "설치가 안 됐다 / doctor가 실패한다" | [§ 문제가 생기면](#문제가-생기면) |
| "완전히 지우고 싶다" | [Privacy FAQ — 완전 삭제](privacy-and-cost.md#완전-삭제) |

## 1단계 — 설치 zip 다운로드

[**🔽 v0.6.2 macOS 설치 zip**][installer-zip]

다운로드한 파일은 보통 `~/Downloads/` 폴더에 저장됩니다.

```text
SynapseMemory-v0.6.2-macos-installer.zip
```

zip 파일을 더블클릭하면 `installer/` 폴더가 생기고 그 안에 다음 파일이 있습니다.

```text
installer/SynapseMemory-Installer.command
```

## 2단계 — `.command` 파일 실행

### 정상적으로 열기

1. Finder에서 `SynapseMemory-Installer.command`를 **우클릭** (또는 Control-클릭)
2. **열기** 선택

### macOS 보안 경고

처음 실행할 때 macOS Gatekeeper가 다음 경고를 보일 수 있습니다.

```text
Apple은 'SynapseMemory-Installer.command'에 악성 코드가 없음을 확인할 수 없습니다.
```

이것은 **악성코드가 아니라**, 설치 파일이 아직 코드사인·공증을 받지 않은 MVP 상태이기 때문에 나오는 정상 경고입니다.

#### 해결 방법 (선택 1)

1. 경고창에서 **완료** 클릭
2. Finder에서 다시 `.command` 파일을 **Control-클릭 → 열기**
3. 경고가 다시 나오면 **열기** 클릭

#### 해결 방법 (선택 2 — "열기" 버튼이 안 보일 때)

1. **시스템 설정 → 개인정보 보호 및 보안 → 보안** 항목으로 이동
2. 아래쪽에 `SynapseMemory-Installer.command`에 대한 메시지가 보이면 **그래도 열기** 클릭
3. 비밀번호 또는 Touch ID 인증

> ⚠️ 신뢰할 수 없는 출처에서 받은 `.command` 파일은 절대 열지 마세요.
> 이 가이드는 GitHub Release에서 직접 받은 공식 설치 파일을 가정합니다.

## 3단계 — 설치 프로그램 진행

`.command`가 열리면 터미널 창이 열리고 설치가 시작됩니다. 설치는 다음 순서로 진행됩니다.

### 3-1. 시작 동의 (GUI 대화창)

> "Synapse Memory 설치를 시작할까요?"

**확인**을 클릭하면 진행됩니다. 취소하면 아무것도 변경되지 않습니다.

### 3-2. Homebrew 점검

이미 설치되어 있으면 건너뜁니다. 없으면 Homebrew를 설치할지 묻습니다.

```text
[1/5] Homebrew 확인 중…
✓ 이미 설치되어 있음 (또는)
→ Homebrew 설치를 시작합니다…
```

### 3-3. Claude Code · Obsidian · apfel 점검

각 도구가 설치되어 있는지 확인합니다. 없으면 설치 진행.

```text
[2/5] Claude Code CLI 확인 중… ✓
[3/5] Obsidian 확인 중…       ✓
[4/5] apfel 확인 중…           ✓
```

### 3-4. Obsidian 저장소(vault) 위치 선택

가장 중요한 단계입니다. **GUI 선택창**이 뜨고 다음 옵션을 보여줍니다.

| 옵션 | 설명 | 추천 여부 |
|---|---|---|
| Obsidian 앱에 이미 등록된 vault | 기존에 쓰던 노트 | 가장 자연스러움 |
| iCloud Drive 아래 기존 vault | iCloud 동기화 중인 노트 | 좋음 |
| **새 vault: `~/iCloud Drive/SynapseVault`** | 새로 시작 + 클라우드 동기화 | **추천** |
| 새 vault: `~/Documents/SynapseVault` | 새로 시작 + 로컬만 | 클라우드 안 쓸 때 |
| 직접 선택 | 임의의 폴더 | 고급 사용자 |

> 💡 **처음 사용자에게는 "새 vault: `~/iCloud Drive/SynapseVault`"를 추천**합니다.
> iCloud 동기화로 노트북을 분실해도 안전합니다.

### 3-5. 환경 점검과 첫 데이터 수집

```text
[5/5] 환경 점검…
✓ apfel 정상
✓ Apple Silicon (M1+)
✓ macOS 26 Tahoe
✓ L0 권한 0700
✓ Claude Code 로그인 확인

✅ 설치 완료. 1분 후 첫 데이터 정리를 시작합니다.
```

## 4단계 — Claude Code에서 첫 질문

Claude Code 앱을 열고 다음 명령을 차례로 실행합니다.

```text
/synapse-doctor
```

화면에 `✓ 준비 완료`가 나오면 정상.

```text
/synapse-daily
```

첫 실행은 1~3분 소요. 다음을 자동으로 합니다.

- Obsidian 노트 모으기
- Claude Code 대화 기록 모으기
- 같은 프로젝트/회사끼리 묶기
- 요약 카드 만들기
- 검색 색인 만들기

이제 자유롭게 질문할 수 있습니다.

```text
/synapse-ask "내가 작년에 어떤 결정 내렸지?"
/synapse-recall "iOS 아키텍처"
/synapse-resume 샘플회사B
```

## 무엇이 어디에 설치되나요?

| 위치 | 내용 |
|---|---|
| `~/.synapse/private/raw/` | 노트와 대화 기록 사본 (외부 차단) |
| `~/.synapse/private/redacted/` | 마스킹된 사본 |
| `~/.synapse/private/rag/` | 검색 색인 |
| 선택한 vault 폴더 | 요약 카드, Profile, 이력서 초안 |
| `~/Library/Logs/SynapseMemory/` | 설치 로그 |

`/opt/homebrew/` 아래에 Homebrew 도구들(apfel 등)이 설치될 수 있습니다.

## 문제가 생기면

### `/synapse-doctor`가 실패할 때

```text
/synapse-fix
```

자동 복구 가능한 항목을 시도합니다 (vault 권한, 로그 디렉터리 등).

### 그래도 안 될 때

1. 설치 로그 확인: `~/Library/Logs/SynapseMemory/install-*.log`
2. GitHub Issues에 위 로그와 함께 보고

## 완전히 삭제하고 싶으면

[Privacy & Cost FAQ — 완전 삭제](privacy-and-cost.md#완전-삭제) 참고.

## 다음에 읽을 문서

- [동작 원리](how-it-works.md) — 설치한 게 무엇을 하는지
- [무엇을 할 수 있는가](what-you-can-do.md) — 실제 활용 사례
- [개인정보 · 비용 · 삭제 FAQ](privacy-and-cost.md)

[installer-zip]: https://github.com/Jimmy-Jung/synapse-memory/releases/download/v0.6.2/SynapseMemory-v0.6.2-macos-installer.zip
