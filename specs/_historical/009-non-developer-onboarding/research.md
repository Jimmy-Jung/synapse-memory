# 조사 기록: 비개발자용 자동 온보딩

**기능**: 009-non-developer-onboarding  
**작성일**: 2026-05-12  
**작성자**: Synapse Memory Maintainers

## R-1 - Runtime bootstrap: PyInstaller보다 uv 우선

- **결정**: MVP는 PyInstaller 단일 binary packaging보다 uv 기반 tool installation/bootstrap을 사용한다.
- **근거**: uv는 Python package의 CLI entrypoint를 `uv tool install`과 `uv tool run`으로 실행/설치할 수 있고, isolated tool environment를 사용하면서 executable을 안정적인 경로에 노출할 수 있다. 이는 현재 Synapse Memory가 이미 Python package로 구성된 상태와 맞다.
- **대안 검토**:
  - PyInstaller: macOS packaging, native dependency, architecture, signing/notarization 부담이 커서 MVP에서 제외.
  - System Python: preinstalled `python3` 의존성을 제거해야 하므로 제외.
- **출처**:
  - uv tools 문서: https://docs.astral.sh/uv/concepts/tools/
  - uv 설치 문서: https://github.com/astral-sh/uv/blob/main/docs/getting-started/installation.md
  - Context7 `/astral-sh/uv`: `uv tool install`은 Python tool executable을 설치하고, `uv tool run`은 isolated environment에서 tool을 실행한다.

## R-2 - 현재 package entrypoint 전략

- **결정**: `synapse-memory`를 canonical CLI로 유지하고, `synapse`는 M1에서 필요성이 검증될 때만 convenience alias로 추가한다.
- **근거**: 현재 `pyproject.toml`에는 이미 `[project.scripts] synapse-memory = "synapse_memory.cli:main"`이 존재한다. 기존 계획의 `scripts/synapse.py` 이동은 현재 브랜치에는 맞지 않는 오래된 전제다.
- **대안 검토**:
  - 모든 user-facing command를 `synapse`로 rename: 기존 docs, slash commands, 사용자를 깨뜨릴 수 있어 제외.
  - `synapse-memory`만 유지: 가능하지만 비개발자 installer UX에서 짧은 alias가 도움이 되는지는 M1 contract test로 판단한다.

## R-3 - apfel packaging 및 배포

- **결정**: MVP에서는 apfel을 plugin zip에 동봉하지 않고 Homebrew로 설치/검증한다.
- **근거**: apfel은 Python package가 아니라 Swift/macOS 26 Apple Intelligence CLI다. 공식 repo와 Homebrew formula는 MIT license, Apple Silicon/macOS 26+ 요구사항, `brew install apfel` 설치 경로를 명시한다.
- **대안 검토**:
  - `bin/` 아래 apfel binary 동봉: release signing, architecture, update 책임이 커져 MVP에서 제외.
  - Python dependency로 추가: apfel은 이 프로젝트 기준 Python CLI package가 아니므로 제외.
  - `Arthur-Ficial/tap/apfel` 사용: Homebrew core formula 반영 지연 시 fallback으로 허용.
- **출처**:
  - apfel GitHub: https://github.com/Arthur-Ficial/apfel
  - Homebrew apfel formula: https://formulae.brew.sh/formula/apfel

## R-4 - Obsidian 및 Claude Code 설치 경로

- **결정**: Obsidian과 Claude Code가 없을 때 MVP installer는 Homebrew cask 경로를 기본으로 사용한다.
- **근거**: Homebrew Cask는 macOS app 설치에 `brew install --cask`를 제공한다. Obsidian과 Claude Code 모두 Homebrew cask page에서 install command를 제공한다.
- **대안 검토**:
  - `.dmg` 직접 다운로드: checksum, mount, copy, Gatekeeper 처리를 직접 구현해야 하므로 MVP에서 제외.
  - 사용자가 먼저 수동 설치: fallback으로는 허용하지만 비개발자 자동 온보딩 목표와 맞지 않는다.
- **출처**:
  - Homebrew Cask 사용법: https://github.com/Homebrew/homebrew-cask/blob/main/USAGE.md
  - Obsidian cask: https://formulae.brew.sh/cask/obsidian
  - Claude Code cask: https://formulae.brew.sh/cask/claude-code

## R-5 - Vault 감지 휴리스틱

- **결정**: 기존 vault 후보는 deterministic order로 감지하고, GUI installer에서는 기존 vault, 추천 iCloud 생성 위치, local Documents fallback, 직접 선택을 함께 제공한다.
- **근거**: Vault 선택은 영향이 크다. 잘못 자동 선택하면 사용자가 의도하지 않은 knowledge base에 Synapse Memory가 연결된다. 비개발자에게는 설치 시점에 저장소 위치를 명확히 고르는 흐름도 필요하며, iCloud Obsidian container가 있으면 sync 가능한 위치를 추천하는 것이 자연스럽다.
- **휴리스틱 순서**:
  1. iCloud Obsidian root: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/*/`
  2. `.obsidian/`을 포함한 Documents vault: `~/Documents/*/`
  3. 관례 경로: `~/Obsidian/`, `~/Documents/Obsidian/`
  4. 기존 환경변수/config path가 있고 여전히 유효한 경우
  5. 새 vault 추천 위치: iCloud Obsidian container가 있으면 `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SynapseVault`, 없으면 `~/Documents/SynapseVault`.
- **대안 검토**:
  - 수동 path 입력만 제공: 비개발자 UX에 맞지 않아 제외.
  - 항상 새 vault 생성: 기존 Obsidian 사용자의 기대와 맞지 않아 제외.

## R-6 - Installer consent model

- **결정**: Installer는 한 번의 setup consent를 받고, 모든 setup apply 작업을 preview한 뒤 audit log를 남긴다. 다만 이 동작은 constitution v1.1.0의 Installation Consent Scoping이 추가될 때까지 release gate로 묶는다.
- **근거**: 단일 동의는 비개발자 UX에 필요하지만, 현재 constitution은 setup consent가 여러 `--apply` 작업을 포괄할 수 있다는 정책을 아직 정의하지 않았다. 구현이 governance보다 앞서면 안 된다.
- **대안 검토**:
  - 영구 per-step confirmation: 안전하지만 이 feature의 핵심 목표를 약화한다.
  - Constitution 개정 없는 단일 consent: 정책 충돌이므로 제외.

## R-7 - `doctor --fix` 복구 경계

- **결정**: Repair는 deterministic local fix whitelist로 구현한다. 기본 `doctor`는 read-only이고, `doctor --fix`만 명시적 apply mode다.
- **근거**: 비개발자에게는 단순한 "고쳐줘" 경로가 필요하지만, 자동 복구가 추측으로 user state를 바꾸면 위험하다. Whitelist는 동작을 테스트 가능하고 감사 가능하게 만든다.
- **자동 복구 후보**:
  - LaunchAgent unloaded -> configured plist load.
  - Vault path missing -> vault 재감지 및 config update.
  - `~/.synapse/private` 권한 drift -> `0700` 복구.
  - Installer-managed command shim 누락 -> runtime bootstrap 재실행.
- **자동 복구 제외**:
  - uv runtime download path 자체 손상 -> installer 재실행 안내.
  - unsupported macOS/Intel Mac -> platform requirement 설명.
  - Apple Intelligence/apfel platform support 없음 -> 요구사항 또는 Homebrew install command 안내.

## R-8 - Gatekeeper 및 배포 형태

- **결정**: MVP는 `.command` 파일과 release zip을 제공하고 Gatekeeper 안내를 문서화한다. Signed/notarized `.pkg`는 후속 track으로 분리한다.
- **근거**: Notarized installer는 더 나은 UX지만 Apple Developer ID, packaging, signing, CI secret이 필요하다. 먼저 onboarding flow 자체를 검증하는 것이 맞다.
- **대안 검토**:
  - 처음부터 `.pkg`: installer behavior 검증 전 배포 pipeline 비용이 커서 제외.
  - CLI docs만 제공: 더블클릭 온보딩 목표를 만족하지 않아 제외.

## R-9 - Codex hook 가용성

- **결정**: Codex SessionEnd hook에 온보딩 성공을 의존하지 않는다. LaunchAgent/polling 기반 자동화와 명시적 CLI command를 사용한다.
- **근거**: 이 repo의 기존 guidance는 Codex hook surface가 Claude Code와 동등하지 않음을 전제로 한다. 온보딩은 unavailable hook에 의존하지 않아야 한다.
- **대안 검토**:
  - Claude-only hook automation: Claude Code와 Codex 양쪽 surface를 지원하는 repo 방향과 맞지 않아 제외.
  - 완전 수동 memory capture: setup 이후 가치가 낮아져 제외.
