#!/usr/bin/env zsh
set -euo pipefail

# Synapse Memory runtime bootstrap.
# 저자: Synapse Memory Maintainers
# 작성일: 2026-05-12

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h}"
SYNAPSE_BIN_DIR="${SYNAPSE_BIN_DIR:-${HOME}/.synapse/bin}"
UV_INSTALL_URL="${SYNAPSE_UV_INSTALL_URL:-https://astral.sh/uv/install.sh}"

mkdir -p "${SYNAPSE_BIN_DIR}"

if ! command -v uv >/dev/null 2>&1 && [ ! -x "${HOME}/.local/bin/uv" ]; then
  echo "[synapse] uv not found. Installing uv..."
  curl -LsSf "${UV_INSTALL_URL}" | sh
fi

cat > "${SYNAPSE_BIN_DIR}/synapse-memory" <<SHIM
#!/usr/bin/env zsh
set -euo pipefail
UV_BIN="\${SYNAPSE_UV_BIN:-\${HOME}/.local/bin/uv}"
if ! command -v "\${UV_BIN}" >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then UV_BIN="\$(command -v uv)"; fi
fi
exec "\${UV_BIN}" tool run --from "${REPO_ROOT}[rag]" synapse-memory "\$@"
SHIM

chmod +x "${SYNAPSE_BIN_DIR}/synapse-memory"

if [ "${SYNAPSE_EXPOSE_SHORT_ALIAS:-0}" = "1" ]; then
  ln -sf "${SYNAPSE_BIN_DIR}/synapse-memory" "${SYNAPSE_BIN_DIR}/synapse"
fi

echo "synapse-memory runtime ready: ${SYNAPSE_BIN_DIR}/synapse-memory"
