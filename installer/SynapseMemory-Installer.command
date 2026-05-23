#!/usr/bin/env zsh
set -euo pipefail

# Synapse Memory non-developer installer skeleton.
# 저자: Synapse Memory Maintainers
# 작성일: 2026-05-12

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h}"
LOG_DIR="${HOME}/Library/Logs/SynapseMemory"
RUN_STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/installer-${RUN_STAMP}.log"
STATE_FILE="${LOG_DIR}/installer-${RUN_STAMP}.state.json"
DRY_RUN="${SYNAPSE_INSTALLER_DRY_RUN:-1}"
ACTIVATE_PLUGINS="${SYNAPSE_ACTIVATE_PLUGINS:-1}"
PLUGIN_SOURCE="${SYNAPSE_PLUGIN_SOURCE:-${REPO_ROOT}}"
CLAUDE_PLUGIN_REF="${SYNAPSE_CLAUDE_PLUGIN_REF:-sm@synapse-memory-marketplace}"
CLAUDE_PLUGIN_SCOPE="${SYNAPSE_CLAUDE_PLUGIN_SCOPE:-user}"
CODEX_PLUGIN_SOURCE="${SYNAPSE_CODEX_PLUGIN_SOURCE:-${PLUGIN_SOURCE}}"
CODEX_PLUGIN_REF="${SYNAPSE_CODEX_PLUGIN_REF:-sm@synapse-memory-marketplace}"
CODEX_MARKETPLACE_NAME="${SYNAPSE_CODEX_MARKETPLACE_NAME:-synapse-memory-marketplace}"
TEST_MODE="${SYNAPSE_INSTALLER_TEST_MODE:-0}"
TEST_ARCH="${SYNAPSE_INSTALLER_TEST_ARCH:-}"

mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"

record_state_step() {
  local step_id="$1"
  local step_status="$2"
  local summary="$3"

  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi

  PYTHONPATH="${REPO_ROOT}/src" python3 - \
    "${STATE_FILE}" \
    "${LOG_FILE}" \
    "${DRY_RUN}" \
    "${step_id}" \
    "${step_status}" \
    "${summary}" <<'PY' >/dev/null 2>&1 || true
from pathlib import Path
import sys

from synapse_memory.installer.state import append_manifest_step

append_manifest_step(
    Path(sys.argv[1]),
    log_path=Path(sys.argv[2]),
    dry_run=sys.argv[3] == "1",
    step_id=sys.argv[4],
    status=sys.argv[5],
    summary=sys.argv[6],
)
PY
}

log_step() {
  local step_id="$1"
  local step_status="$2"
  local summary="$3"
  printf '%s %s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${step_id}" "${step_status}" "${summary}" | tee -a "${LOG_FILE}"
  record_state_step "${step_id}" "${step_status}" "${summary}"
}

obsidian_bundle_is_valid() {
  local app_path="/Applications/Obsidian.app"
  local bundle_id
  if [ ! -d "${app_path}" ]; then
    return 1
  fi
  bundle_id="$(/usr/libexec/PlistBuddy -c "Print CFBundleIdentifier" "${app_path}/Contents/Info.plist" 2>/dev/null || true)"
  [ "${bundle_id}" = "md.obsidian" ]
}

detect_dependency() {
  local item="$1"
  case "${item}" in
    obsidian)
      if brew list --cask obsidian >/dev/null 2>&1; then
        log_step "detect_obsidian" "success" "installed=true source=homebrew"
        return 0
      fi
      if obsidian_bundle_is_valid; then
        log_step "detect_obsidian" "success" "installed=true source=/Applications/Obsidian.app"
        return 0
      fi
      return 1
      ;;
    claude-code)
      if brew list --cask claude-code >/dev/null 2>&1; then
        log_step "detect_claude-code" "success" "installed=true source=homebrew"
        return 0
      fi
      if command -v claude >/dev/null 2>&1; then
        log_step "detect_claude-code" "success" "installed=true path=$(command -v claude)"
        return 0
      fi
      return 1
      ;;
    apfel)
      if brew list --formula apfel >/dev/null 2>&1 || command -v apfel >/dev/null 2>&1; then
        log_step "detect_apfel" "success" "installed=true"
        return 0
      fi
      return 1
      ;;
  esac
  return 1
}

install_dependency() {
  local item="$1"
  case "${item}" in
    obsidian)
      if [ -d "/Applications/Obsidian.app" ]; then
        log_step "install_obsidian" "failed" "existing app is not a recognized Obsidian bundle"
        /usr/bin/osascript -e 'display alert "Obsidian.app이 이미 있지만 정식 Obsidian 앱으로 확인되지 않아 설치를 중단합니다. 기존 앱을 직접 확인한 뒤 다시 실행하세요."'
        exit 1
      fi
      brew install --cask obsidian
      ;;
    claude-code)
      brew install --cask claude-code
      ;;
    apfel)
      brew install apfel
      ;;
  esac
  log_step "install_${item}" "success" "installed=true"
}

ask_consent() {
  if [ "${TEST_MODE}" = "1" ]; then
    return 0
  fi

  /usr/bin/osascript <<'APPLESCRIPT'
display dialog "Synapse Memory 설치를 시작합니다.

이 설치는 Homebrew/Obsidian/Claude Code/apfel/Synapse runtime을 확인하고, Obsidian Vault를 감지하거나 생성할 수 있습니다.

운영 단계의 메모리 쓰기 작업은 이 동의에 포함되지 않습니다." buttons {"취소", "동의"} default button "동의" cancel button "취소" with title "Synapse Memory Installer"
APPLESCRIPT
}

choose_vault_line() {
  local choices_file="$1"
  if [ "${TEST_MODE}" = "1" ]; then
    head -n 1 "${choices_file}"
    return 0
  fi

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
  if [ "${TEST_MODE}" = "1" ]; then
    printf '%s\n' "${HOME}/SynapseVault"
    return 0
  fi

  /usr/bin/osascript <<'APPLESCRIPT'
set pickedFolder to choose folder with prompt "Synapse Memory 저장소로 사용할 폴더를 선택하세요."
return POSIX path of pickedFolder
APPLESCRIPT
}

claude_plugin_installed() {
  claude plugin list 2>/dev/null | grep -q "${CLAUDE_PLUGIN_REF}"
}

claude_plugin_enabled() {
  claude plugin list 2>/dev/null | awk -v plugin="${CLAUDE_PLUGIN_REF}" '
    index($0, plugin) { found = 1; next }
    found && /Status:/ {
      if ($0 ~ /enabled/) { enabled = 1 }
      exit
    }
    END { exit enabled ? 0 : 1 }
  '
}

activate_claude_plugin() {
  if ! command -v claude >/dev/null 2>&1; then
    log_step "activate_claude_plugin" "skipped" "claude CLI not found"
    return 0
  fi

  if [ ! -f "${REPO_ROOT}/.claude-plugin/marketplace.json" ]; then
    log_step "activate_claude_plugin" "failed" "missing .claude-plugin/marketplace.json"
    return 1
  fi

  if claude plugin validate "${REPO_ROOT}" >>"${LOG_FILE}" 2>&1; then
    log_step "validate_claude_plugin" "success" "source=${REPO_ROOT}"
  else
    log_step "validate_claude_plugin" "failed" "source=${REPO_ROOT}"
    return 1
  fi

  if claude plugin marketplace list 2>/dev/null | grep -q "synapse-memory-marketplace"; then
    log_step "add_claude_marketplace" "success" "already_configured=true"
  else
    if claude plugin marketplace add --scope "${CLAUDE_PLUGIN_SCOPE}" "${PLUGIN_SOURCE}" >>"${LOG_FILE}" 2>&1; then
      log_step "add_claude_marketplace" "success" "source=${PLUGIN_SOURCE} scope=${CLAUDE_PLUGIN_SCOPE}"
    else
      log_step "add_claude_marketplace" "failed" "source=${PLUGIN_SOURCE} scope=${CLAUDE_PLUGIN_SCOPE}"
      return 1
    fi
  fi

  if claude_plugin_installed; then
    log_step "install_claude_plugin" "success" "already_installed=true plugin=${CLAUDE_PLUGIN_REF}"
  else
    if claude plugin install --scope "${CLAUDE_PLUGIN_SCOPE}" "${CLAUDE_PLUGIN_REF}" >>"${LOG_FILE}" 2>&1; then
      log_step "install_claude_plugin" "success" "plugin=${CLAUDE_PLUGIN_REF} scope=${CLAUDE_PLUGIN_SCOPE}"
    else
      log_step "install_claude_plugin" "failed" "plugin=${CLAUDE_PLUGIN_REF} scope=${CLAUDE_PLUGIN_SCOPE}"
      return 1
    fi
  fi

  if claude_plugin_enabled; then
    log_step "enable_claude_plugin" "success" "already_enabled=true plugin=${CLAUDE_PLUGIN_REF}"
  else
    if claude plugin enable --scope "${CLAUDE_PLUGIN_SCOPE}" "${CLAUDE_PLUGIN_REF}" >>"${LOG_FILE}" 2>&1; then
      log_step "enable_claude_plugin" "success" "plugin=${CLAUDE_PLUGIN_REF} scope=${CLAUDE_PLUGIN_SCOPE}"
    else
      log_step "enable_claude_plugin" "failed" "plugin=${CLAUDE_PLUGIN_REF} scope=${CLAUDE_PLUGIN_SCOPE}"
      return 1
    fi
  fi
}

activate_codex_plugin() {
  local prompt_input_file
  local codex_config_path

  if ! command -v codex >/dev/null 2>&1; then
    log_step "activate_codex_plugin" "skipped" "codex CLI not found"
    return 0
  fi

  if [ ! -f "${REPO_ROOT}/.codex-plugin/plugin.json" ]; then
    log_step "activate_codex_plugin" "failed" "missing .codex-plugin/plugin.json"
    return 1
  fi

  if codex plugin marketplace add "${CODEX_PLUGIN_SOURCE}" >>"${LOG_FILE}" 2>&1; then
    log_step "add_codex_marketplace" "success" "source=${CODEX_PLUGIN_SOURCE}"
  else
    log_step "add_codex_marketplace" "warning" "source=${CODEX_PLUGIN_SOURCE}; checking existing plugin visibility"
  fi

  codex_config_path="${CODEX_CONFIG_PATH:-${HOME}/.codex/config.toml}"
  install_codex_plugin_cache
  ensure_codex_plugin_enabled "${codex_config_path}"

  # 이 시점에서 plugin cache(install_codex_plugin_cache) 와 config 활성화
  # (ensure_codex_plugin_enabled) 는 이미 성공한 상태다. verify 는 Codex CLI 가
  # 실제로 plugin 을 surface 하는지 확인하는 보조 검사일 뿐이므로, 검사 실패가
  # 전체 install 을 중단시키지 않도록 warning 으로 강등한다.
  #
  # 추가로 Codex 0.122.0 부터는 plugin skill 이 "<plugin>:<skill>" prefix 없이
  # <plugins_instructions> 섹션에만 등장하는 경우가 있어 단일 "sm:sm" grep 으로는
  # 정상 활성화 상태에서도 false negative 가 난다. 다중 signal 중 하나라도 매칭되면
  # 가시 상태로 간주한다.
  prompt_input_file="$(mktemp)"
  if codex debug prompt-input "Synapse Memory plugin visibility check" >"${prompt_input_file}" 2>>"${LOG_FILE}"; then
    if grep -qE 'sm:sm|sm@synapse-memory-marketplace|Synapse Memory' "${prompt_input_file}"; then
      log_step "verify_codex_plugin" "success" "prompt_visible=true"
      rm -f "${prompt_input_file}"
      return 0
    fi
    log_step "verify_codex_plugin" "warning" "prompt_visible=false; plugin enabled in config/cache but not surfaced by codex debug prompt-input"
  else
    log_step "verify_codex_plugin" "warning" "codex debug prompt-input failed; plugin enabled in config/cache"
  fi
  rm -f "${prompt_input_file}"
  return 0
}

codex_plugin_manifest_value() {
  local key="$1"
  sed -n "s/^[[:space:]]*\"${key}\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "${REPO_ROOT}/.codex-plugin/plugin.json" | head -n 1
}

install_codex_plugin_cache() {
  local codex_home
  local plugin_name
  local plugin_version
  local cache_dir
  local cache_parent

  codex_home="${CODEX_HOME:-${HOME}/.codex}"
  plugin_name="$(codex_plugin_manifest_value "name")"
  plugin_version="$(codex_plugin_manifest_value "version")"

  if [ -z "${plugin_name}" ] || [ -z "${plugin_version}" ]; then
    log_step "install_codex_plugin_cache" "failed" "invalid .codex-plugin/plugin.json"
    return 1
  fi

  cache_dir="${codex_home}/plugins/cache/${CODEX_MARKETPLACE_NAME}/${plugin_name}/${plugin_version}"
  cache_parent="$(dirname "${cache_dir}")"
  mkdir -p "${cache_parent}"

  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude ".git/" \
      --exclude ".agents/" \
      --exclude ".claude/" \
      --exclude ".codex/" \
      --exclude ".specify/" \
      --exclude ".pytest_cache/" \
      --exclude "__pycache__/" \
      --exclude ".venv/" \
      "${REPO_ROOT}/" "${cache_dir}/" >>"${LOG_FILE}" 2>&1
  else
    rm -rf "${cache_dir}"
    mkdir -p "${cache_dir}"
    cp -R "${REPO_ROOT}/." "${cache_dir}/"
    rm -rf \
      "${cache_dir}/.git" \
      "${cache_dir}/.agents" \
      "${cache_dir}/.claude" \
      "${cache_dir}/.codex" \
      "${cache_dir}/.specify" \
      "${cache_dir}/.pytest_cache" \
      "${cache_dir}/.venv"
    find "${cache_dir}" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
  fi

  cat > "${cache_dir}/.codex-marketplace-install.json" <<JSON
{
  "source_type": "local",
  "source": "${REPO_ROOT}",
  "ref_name": null,
  "sparse_paths": [],
  "revision": null
}
JSON
  log_step "install_codex_plugin_cache" "success" "path=${cache_dir}"
}

ensure_codex_plugin_enabled() {
  local config_path="$1"
  local config_dir

  config_dir="$(dirname "${config_path}")"
  mkdir -p "${config_dir}"
  touch "${config_path}"

  if command -v python3 >/dev/null 2>&1; then
    python3 - "${config_path}" "${CODEX_PLUGIN_REF}" >>"${LOG_FILE}" 2>&1 <<'PY'
from __future__ import annotations

import datetime as dt
import shutil
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
plugin_ref = sys.argv[2]
section = f'[plugins."{plugin_ref}"]'
original = path.read_text(encoding="utf-8") if path.exists() else ""
lines = original.splitlines()
changed = False

if section not in lines:
    new_text = original.rstrip() + f"\n\n{section}\nenabled = true\n"
    changed = True
else:
    output: list[str] = []
    in_section = False
    saw_enabled = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not saw_enabled:
                output.append("enabled = true")
                changed = True
            in_section = stripped == section
            saw_enabled = False
            output.append(line)
            continue
        if in_section and stripped.startswith("enabled"):
            if stripped != "enabled = true":
                changed = True
            output.append("enabled = true")
            saw_enabled = True
            continue
        output.append(line)
    if in_section and not saw_enabled:
        output.append("enabled = true")
        changed = True
    new_text = "\n".join(output) + "\n"
    changed = changed or new_text != original

if changed:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.synapse-backup-{timestamp}")
    shutil.copy2(path, backup)
    path.write_text(new_text, encoding="utf-8")
    print(f"codex_plugin_config changed=true backup={backup}")
else:
    print("codex_plugin_config changed=false")
PY
    log_step "enable_codex_plugin" "success" "config=${config_path} plugin=${CODEX_PLUGIN_REF}"
    return 0
  fi

  if grep -q "^\[plugins.\"${CODEX_PLUGIN_REF}\"\]" "${config_path}"; then
    log_step "enable_codex_plugin" "success" "config=${config_path} already_configured=true"
    return 0
  fi

  cp "${config_path}" "${config_path}.synapse-backup-$(date +%Y%m%d-%H%M%S)"
  {
    printf '\n[plugins."%s"]\n' "${CODEX_PLUGIN_REF}"
    printf 'enabled = true\n'
  } >>"${config_path}"
  log_step "enable_codex_plugin" "success" "config=${config_path} plugin=${CODEX_PLUGIN_REF}"
}

activate_plugins() {
  activate_claude_plugin
  activate_codex_plugin
}

notify_user() {
  local message="$1"
  if [ "${TEST_MODE}" = "1" ]; then
    printf '%s notify skipped test_mode=true message=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${message}" | tee -a "${LOG_FILE}"
    return 0
  fi
  /usr/bin/osascript -e "display notification \"${message}\" with title \"Synapse Memory\""
}

alert_user() {
  local message="$1"
  if [ "${TEST_MODE}" = "1" ]; then
    log_step "alert" "skipped" "test_mode=true message=${message}"
    return 0
  fi
  /usr/bin/osascript -e "display alert \"${message}\""
}

log_step "start" "success" "log=${LOG_FILE} state=${STATE_FILE}"

if ! ask_consent >/dev/null; then
  log_step "consent" "cancelled" "user_cancelled=true"
  notify_user "설치가 취소되었습니다."
  exit 130
fi
log_step "consent" "success" "scope=setup"

if [ "${TEST_ARCH:-$(uname -m)}" != "arm64" ]; then
  log_step "platform" "failed" "Apple Silicon arm64 required"
  alert_user "Synapse Memory는 Apple Silicon Mac이 필요합니다."
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
    if detect_dependency "${item}"; then
      true
    else
      if [ "${DRY_RUN}" = "1" ]; then
        log_step "install_${item}" "preview" "would install ${item}"
      else
        install_dependency "${item}"
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

if [ "${ACTIVATE_PLUGINS}" = "1" ]; then
  if [ "${DRY_RUN}" = "1" ]; then
    log_step "activate_claude_plugin" "preview" "would add marketplace and enable ${CLAUDE_PLUGIN_REF}"
    log_step "activate_codex_plugin" "preview" "would add Codex marketplace from ${CODEX_PLUGIN_SOURCE} and enable ${CODEX_PLUGIN_REF}"
  else
    activate_plugins
  fi
else
  log_step "activate_plugins" "skipped" "SYNAPSE_ACTIVATE_PLUGINS=${ACTIVATE_PLUGINS}"
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
    log_step "vault_config" "preview" "would write vault to ~/.synapse/config.yaml"
  else
    mkdir -p "${SELECTED_VAULT}/.obsidian"
    log_step "vault_setup" "success" "prepared=${SELECTED_VAULT}"

    # bootstrap_runtime 이 ~/.synapse/bin/synapse-memory 를 깔아둔 경우, 사용자가
    # 다음 doctor 실행에서 "config.yaml vault 미설정" 경고로 막히지 않도록
    # vault 경로를 runtime config 에 자동 기록한다. 이전에는 vault_setup 이
    # .obsidian 디렉터리만 생성하고 끝나서 사용자가 수동으로
    # `synapse-memory config set vault <path>` 를 호출해야 했다.
    synapse_runtime_bin="${HOME}/.synapse/bin/synapse-memory"
    if [ -x "${synapse_runtime_bin}" ]; then
      if "${synapse_runtime_bin}" config set vault "${SELECTED_VAULT}" >>"${LOG_FILE}" 2>&1; then
        log_step "vault_config" "success" "path=${SELECTED_VAULT}"
      else
        log_step "vault_config" "warning" "synapse-memory config set vault failed; run manually after install"
      fi
    else
      log_step "vault_config" "skipped" "synapse-memory runtime not available at ${synapse_runtime_bin}"
    fi
  fi
else
  log_step "vault_detection" "skipped" "python3 unavailable before runtime bootstrap"
fi

log_step "complete" "success" "dry_run=${DRY_RUN} state=${STATE_FILE}"
notify_user "Synapse Memory 설치 점검이 완료되었습니다. 로그: ${LOG_FILE} 상태: ${STATE_FILE}"
