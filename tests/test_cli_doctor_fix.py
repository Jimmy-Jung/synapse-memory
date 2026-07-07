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
from synapse_memory.model import Entity
from synapse_memory.store import save_page


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
    ok_diag = DiagnosticResult("test", DiagnosticStatus.OK, "ok")

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
        lambda: SimpleNamespace(
            vault=str(tmp_path),
            maintenance=SimpleNamespace(engine="claude"),
        ),
    )
    monkeypatch.setattr(cli_mod, "diagnose_wiki_pages", lambda _vault: ok_diag)
    monkeypatch.setattr(cli_mod, "diagnose_wiki_maintenance", lambda: ok_diag)
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
    assert "privacy mode ingest: raw_or_sampled_raw_to_provider" in out
    assert "privacy mode query: wiki_cards_and_approved_profile_to_provider" in out
    assert "Claude Code hook 미설치" in out
    assert "synapse-memory hook install" in out


def test_cmd_doctor_reports_hook_not_ready_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ok_diag = DiagnosticResult("test", DiagnosticStatus.OK, "ok")

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
        lambda: SimpleNamespace(
            vault=str(tmp_path),
            maintenance=SimpleNamespace(engine="claude"),
        ),
    )
    monkeypatch.setattr(cli_mod, "diagnose_wiki_pages", lambda _vault: ok_diag)
    monkeypatch.setattr(cli_mod, "diagnose_wiki_maintenance", lambda: ok_diag)
    monkeypatch.setattr(
        cli_mod,
        "diagnose_vault_config_consistency",
        lambda _vault: ok_diag,
    )
    monkeypatch.setattr(
        "synapse_memory.hooks.install.diagnose_session_hook",
        lambda: SimpleNamespace(
            installed=True,
            ready=False,
            message="hook 설치됨; 현재 프로젝트 미등록",
        ),
    )

    rc = cmd_doctor(argparse.Namespace(fix=False, fix_config=False, yes=False))

    assert rc == 0
    out = capsys.readouterr().out
    assert "현재 프로젝트 미등록" in out
    assert "synapse-memory setup" in out
    assert "--no-marker" not in out
    assert "synapse-memory context render" in out


def test_cmd_doctor_reports_relation_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ok_diag = DiagnosticResult("test", DiagnosticStatus.OK, "ok")
    save_page(
        Entity(type="project", slug="synapse-memory", title="Synapse Memory", uses=("rag",)),
        vault_path=tmp_path,
    )

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
        lambda: SimpleNamespace(
            vault=str(tmp_path),
            maintenance=SimpleNamespace(engine="claude"),
        ),
    )
    monkeypatch.setattr(cli_mod, "diagnose_wiki_pages", lambda _vault: ok_diag)
    monkeypatch.setattr(cli_mod, "diagnose_wiki_maintenance", lambda: ok_diag)
    monkeypatch.setattr(
        cli_mod,
        "diagnose_vault_config_consistency",
        lambda _vault: ok_diag,
    )
    monkeypatch.setattr(
        "synapse_memory.hooks.install.diagnose_session_hook",
        lambda: SimpleNamespace(installed=True, ready=True, message="hook ok"),
    )

    rc = cmd_doctor(argparse.Namespace(fix=False, fix_config=False, yes=False))

    assert rc == 0
    out = capsys.readouterr().out
    assert "typed_relation_coverage: 100.0% (1/1)" in out
    assert "legacy_related_residual: 0 (0.0%)" in out
    assert "orphan_ratio: 0.0% (0/1)" in out
