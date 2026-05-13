"""Runtime bootstrap 계약 helper.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def managed_bin_dir(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return root / ".synapse" / "bin"


@dataclass(frozen=True)
class BootstrapPlan:
    project_source: str
    command: str = "synapse-memory"
    expose_synapse_alias: bool = False


def build_synapse_shim(
    *,
    project_source: str,
    executable: str = "synapse-memory",
) -> str:
    """system python 대신 uv tool run을 사용하는 command shim."""
    return "\n".join(
        [
            "#!/usr/bin/env zsh",
            "# executes via uv tool run; does not call system python directly",
            "set -euo pipefail",
            'UV_BIN="${SYNAPSE_UV_BIN:-${HOME}/.local/bin/uv}"',
            'if ! command -v "$UV_BIN" >/dev/null 2>&1; then',
            '  if command -v uv >/dev/null 2>&1; then UV_BIN="$(command -v uv)"; fi',
            "fi",
            f'exec "$UV_BIN" tool run --from "{project_source}" {executable} "$@"',
            "",
        ]
    )


def render_bootstrap_script(plan: BootstrapPlan) -> str:
    alias_block = ""
    if plan.expose_synapse_alias:
        alias_block = (
            '\nln -sf "${SYNAPSE_BIN_DIR}/synapse-memory" '
            '"${SYNAPSE_BIN_DIR}/synapse"\n'
        )
    return f"""#!/usr/bin/env zsh
set -euo pipefail

SYNAPSE_BIN_DIR="${{SYNAPSE_BIN_DIR:-${{HOME}}/.synapse/bin}}"
UV_INSTALL_URL="${{SYNAPSE_UV_INSTALL_URL:-https://astral.sh/uv/install.sh}}"
mkdir -p "${{SYNAPSE_BIN_DIR}}"

if ! command -v uv >/dev/null 2>&1 && [ ! -x "${{HOME}}/.local/bin/uv" ]; then
  curl -LsSf "${{UV_INSTALL_URL}}" | sh
fi

cat > "${{SYNAPSE_BIN_DIR}}/synapse-memory" <<'SHIM'
{build_synapse_shim(project_source=plan.project_source, executable=plan.command).rstrip()}
SHIM
chmod +x "${{SYNAPSE_BIN_DIR}}/synapse-memory"
{alias_block}
echo "synapse-memory runtime ready: ${{SYNAPSE_BIN_DIR}}/synapse-memory"
"""
