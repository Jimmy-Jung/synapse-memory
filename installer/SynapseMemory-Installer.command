#!/usr/bin/env zsh
set -euo pipefail

# Synapse Memory non-developer installer skeleton.
# 저자: Synapse Memory Maintainers
# 작성일: 2026-05-12

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h}"
LOG_DIR="${HOME}/Library/Logs/SynapseMemory"
LOG_FILE="${LOG_DIR}/installer-$(date +%Y%m%d-%H%M%S).log"
DRY_RUN="${SYNAPSE_INSTALLER_DRY_RUN:-1}"

mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"

log_step() {
  local step_id="$1"
  local status="$2"
  local summary="$3"
  printf '%s %s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${step_id}" "${status}" "${summary}" | tee -a "${LOG_FILE}"
}

ask_consent() {
  /usr/bin/osascript <<'APPLESCRIPT'
display dialog "Synapse Memory 설치를 시작합니다.

이 설치는 Homebrew/Obsidian/Claude Code/apfel/Synapse runtime을 확인하고, Obsidian Vault를 감지하거나 생성할 수 있습니다.

운영 단계의 메모리 쓰기 작업은 이 동의에 포함되지 않습니다." buttons {"취소", "동의"} default button "동의" cancel button "취소" with title "Synapse Memory Installer"
APPLESCRIPT
}

choose_vault_line() {
  local choices_file="$1"
  /usr/bin/osascript <<APPLESCRIPT
set choicesPath to POSIX file "${choices_file}"
set rawText to read choicesPath as «class utf8»
set choicesList to paragraphs of rawText
set picked to choose from list choicesList with prompt "Synapse Memory 저장소로 사용할 Obsidian Vault 위치를 선택하세요. 추천 위치는 iCloud Obsidian 폴더입니다." with title "Synapse Memory Vault 선택" OK button name "선택" cancel button name "취소"
if picked is false then error number -128
return item 1 of picked
APPLESCRIPT
}

choose_custom_vault_path() {
  /usr/bin/osascript <<'APPLESCRIPT'
set pickedFolder to choose folder with prompt "Synapse Memory 저장소로 사용할 폴더를 선택하세요."
return POSIX path of pickedFolder
APPLESCRIPT
}

log_step "start" "success" "log=${LOG_FILE}"

if ! ask_consent >/dev/null; then
  log_step "consent" "cancelled" "user_cancelled=true"
  /usr/bin/osascript -e 'display notification "설치가 취소되었습니다." with title "Synapse Memory"'
  exit 130
fi
log_step "consent" "success" "scope=setup"

if [ "$(uname -m)" != "arm64" ]; then
  log_step "platform" "failed" "Apple Silicon arm64 required"
  /usr/bin/osascript -e 'display alert "Synapse Memory는 Apple Silicon Mac이 필요합니다."'
  exit 1
fi
log_step "platform" "success" "arch=arm64"

for tool in brew; do
  if command -v "${tool}" >/dev/null 2>&1; then
    log_step "detect_${tool}" "success" "path=$(command -v "${tool}")"
  else
    log_step "detect_${tool}" "failed" "${tool} not found"
  fi
done

if command -v brew >/dev/null 2>&1; then
  for item in obsidian claude-code apfel; do
    if brew list --formula "${item}" >/dev/null 2>&1 || brew list --cask "${item}" >/dev/null 2>&1; then
      log_step "detect_${item}" "success" "installed=true"
    else
      if [ "${DRY_RUN}" = "1" ]; then
        log_step "install_${item}" "preview" "would install ${item}"
      else
        case "${item}" in
          obsidian|claude-code) brew install --cask "${item}" ;;
          apfel) brew install apfel ;;
        esac
        log_step "install_${item}" "success" "installed=true"
      fi
    fi
  done
fi

if [ "${DRY_RUN}" = "1" ]; then
  log_step "bootstrap_runtime" "preview" "would run scripts/bootstrap_runtime.sh"
else
  "${REPO_ROOT}/scripts/bootstrap_runtime.sh" 2>&1 | tee -a "${LOG_FILE}"
  log_step "bootstrap_runtime" "success" "runtime_ready=true"
fi

if command -v python3 >/dev/null 2>&1; then
  VAULT_CHOICES_FILE="$(mktemp)"
  PYTHONPATH="${REPO_ROOT}/src" python3 - <<'PY' > "${VAULT_CHOICES_FILE}"
from synapse_memory.vault_detector import installer_vault_choices

for candidate in installer_vault_choices():
    if candidate.needs_creation:
        label = f"{candidate.display_name} | {candidate.path}"
    else:
        label = f"기존 Vault: {candidate.display_name} | {candidate.path}"
    print(f"{label}\t{candidate.path}\t{int(candidate.needs_creation)}")
print("직접 선택...\t__CUSTOM__\t0")
PY
  SELECTED_LINE="$(choose_vault_line "${VAULT_CHOICES_FILE}")"
  SELECTED_VAULT="$(printf '%s' "${SELECTED_LINE}" | awk -F '\t' '{print $2}')"
  NEEDS_CREATION="$(printf '%s' "${SELECTED_LINE}" | awk -F '\t' '{print $3}')"
  rm -f "${VAULT_CHOICES_FILE}"

  if [ "${SELECTED_VAULT}" = "__CUSTOM__" ]; then
    SELECTED_VAULT="$(choose_custom_vault_path)"
    NEEDS_CREATION="0"
  fi

  log_step "vault_selection" "success" "path=${SELECTED_VAULT} needs_creation=${NEEDS_CREATION}"
  if [ "${DRY_RUN}" = "1" ]; then
    log_step "vault_setup" "preview" "would prepare vault at ${SELECTED_VAULT}"
  else
    mkdir -p "${SELECTED_VAULT}/.obsidian"
    log_step "vault_setup" "success" "prepared=${SELECTED_VAULT}"
  fi
else
  log_step "vault_detection" "skipped" "python3 unavailable before runtime bootstrap"
fi

log_step "complete" "success" "dry_run=${DRY_RUN}"
/usr/bin/osascript -e "display notification \"Synapse Memory 설치 점검이 완료되었습니다. 로그: ${LOG_FILE}\" with title \"Synapse Memory\""
