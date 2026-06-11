"""Doctor --fix CLI 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import synapse_memory.cli as cli_mod
from synapse_memory.cli import cmd_doctor
from synapse_memory.doctor import DiagnosticResult, DiagnosticStatus


def test_parser_has_doctor_fix() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["doctor", "--fix"])

    assert args.func is cmd_doctor
    assert args.fix is True


def test_cmd_doctor_fix_delegates_to_repair_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, bool] = {}

    def fake_fix(*, assume_yes: bool = False) -> int:
        called["fix"] = True
        called["assume_yes"] = assume_yes
        return 0

    monkeypatch.setattr(cli_mod, "run_doctor_fix", fake_fix)

    rc = cmd_doctor(argparse.Namespace(fix=True, yes=True))

    assert rc == 0
    assert called == {"fix": True, "assume_yes": True}


def test_cmd_doctor_reports_hook_install_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    l0 = tmp_path / ".synapse" / "private"
    l0.mkdir(parents=True)
    l0.chmod(0o700)
    ok_diag = DiagnosticResult("test", DiagnosticStatus.OK, "ok")

    monkeypatch.setattr(
        cli_mod,
        "detect_environment",
        lambda: SimpleNamespace(
            apfel_path=Path("/usr/local/bin/apfel"),
            apfel_version="1.0",
            is_apple_silicon=True,
            macos_major=26,
            macos_version="26.0",
            ready=True,
        ),
    )
    monkeypatch.setattr(cli_mod, "ensure_l0_root_secure", lambda: l0)
    monkeypatch.setattr(
        cli_mod,
        "detect_ai_environment",
        lambda: SimpleNamespace(
            ready=True,
            provider="claude",
            path="/usr/local/bin/claude",
            version="1.0",
            model=None,
        ),
    )
    monkeypatch.setattr(
        "synapse_memory.config.load_config",
        lambda: SimpleNamespace(vault=str(tmp_path)),
    )
    monkeypatch.setattr(
        "synapse_memory.doctor.diagnose_private_folder_deny",
        lambda _vault: ok_diag,
    )
    monkeypatch.setattr(
        "synapse_memory.doctor.diagnose_dataview_plugin",
        lambda _vault: ok_diag,
    )
    monkeypatch.setattr(
        cli_mod,
        "diagnose_vault_config_consistency",
        lambda _vault: ok_diag,
    )
    monkeypatch.setattr(
        "synapse_memory.hooks.install.diagnose_session_hook",
        lambda: SimpleNamespace(installed=False, message="Claude Code hook 미설치"),
    )

    rc = cmd_doctor(argparse.Namespace(fix=False, fix_config=False, yes=False))

    assert rc == 0
    out = capsys.readouterr().out
    assert "Claude Code hook 미설치" in out
    assert "synapse-memory hook install" in out
