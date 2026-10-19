"""codex 모델 카탈로그 — 우선순위 기반 제안, 사라진 모델 대체, refresh/doctor 연동."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import synapse_memory.cli as cli
from synapse_memory.config import ModelsConfig
from synapse_memory.doctor import DiagnosticStatus, diagnose_codex_models
from synapse_memory.llm import codex_catalog
from synapse_memory.llm.codex import CodexEnvironment, complete

# 실측 카탈로그(2026-10-19) 축약 — 세대마다 티어 구성이 다르다(6세대 terra 없음).
_CATALOG = [
    {"slug": "gpt-6-luna", "visibility": "list", "priority": 4},
    {"slug": "gpt-6.1-sol", "visibility": "list", "priority": 1},
    {"slug": "gpt-reserve", "visibility": "hide", "priority": 4},
    {"slug": "gpt-6-astra", "visibility": "list", "priority": 2},
    {"slug": "gpt-5.6-luna", "visibility": "list", "priority": 9},
]


@pytest.fixture
def catalog(monkeypatch):
    def _set(models=_CATALOG):
        raw = json.dumps({"models": models}) if models is not None else None
        monkeypatch.setattr(codex_catalog, "_run_catalog", lambda: raw)
        codex_catalog.load_catalog.cache_clear()

    _set()
    return _set


@pytest.fixture
def isolated_config(monkeypatch, tmp_path) -> Path:
    import synapse_memory.config as config_module

    path = tmp_path / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", path)
    return path


def test_load_catalog_lists_visible_models_by_priority(catalog) -> None:
    assert codex_catalog.load_catalog() == (
        "gpt-6.1-sol",
        "gpt-6-astra",
        "gpt-6-luna",
        "gpt-5.6-luna",
    )


@pytest.mark.parametrize("raw", [None, "not json", '{"models": [{"slug": "x"}]}', "[]"])
def test_load_catalog_returns_none_on_failure(monkeypatch, raw) -> None:
    monkeypatch.setattr(codex_catalog, "_run_catalog", lambda: raw)
    codex_catalog.load_catalog.cache_clear()
    assert codex_catalog.load_catalog() is None


def test_propose_maps_priority_one_and_latest_luna() -> None:
    proposal = codex_catalog.propose(("gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-luna"))
    assert proposal["default"] == proposal["card_generate"] == proposal["ask"] == "gpt-6.1-sol"
    assert proposal["classify"] == proposal["relevance"] == "gpt-6-luna"
    # luna가 없으면 저가도 1순위
    assert codex_catalog.propose(("gpt-7",))["classify"] == "gpt-7"


def test_pending_changes_and_apply_on_default_config(catalog) -> None:
    models = ModelsConfig()
    changes = codex_catalog.pending_changes(models, codex_catalog.load_catalog())
    assert ("card_generate", "gpt-5.6-terra", "gpt-6.1-sol") in changes
    assert ("classify", "gpt-5.6-luna", "gpt-6-luna") in changes

    codex_catalog.apply_changes(models, changes)
    assert codex_catalog.pending_changes(models, codex_catalog.load_catalog()) == []


def test_replacement_for_missing_models_only(catalog, capsys) -> None:
    assert codex_catalog.replacement_for("gpt-6-astra") is None
    assert codex_catalog.replacement_for("gpt-5.6-terra") == "gpt-6.1-sol"
    assert codex_catalog.replacement_for("gpt-5.5-luna") == "gpt-6-luna"
    assert "gpt-5.6-terra" in capsys.readouterr().err

    catalog(None)  # 조회 실패 → 기존 설정 유지
    assert codex_catalog.replacement_for("gpt-5.6-terra") is None


def test_codex_call_uses_replacement_model(catalog, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "private"))
    seen = []

    def fake_run(args, **_kwargs):
        seen.append(args[args.index("-m") + 1])
        out_path = args[args.index("--output-last-message") + 1]
        Path(out_path).write_text("ok", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    env = CodexEnvironment("/opt/homebrew/bin/codex", "codex 1.0", "gpt-5.6-terra")
    with patch("synapse_memory.llm.codex.subprocess.run", side_effect=fake_run):
        assert complete("prompt", env=env) == "ok"
        assert complete("prompt", env=env, model="gpt-6-astra") == "ok"

    assert seen == ["gpt-6.1-sol", "gpt-6-astra"]


def test_cli_models_refresh_yes_saves_and_dry_run_does_not(catalog, isolated_config, capsys):
    from synapse_memory.config import load_config

    assert cli.main(["models", "refresh", "--dry-run"]) == 0
    assert "gpt-5.6-terra → gpt-6.1-sol" in capsys.readouterr().out
    assert not isolated_config.exists()

    assert cli.main(["models", "refresh", "--yes"]) == 0
    assert load_config().models.overrides.codex.card_generate == "gpt-6.1-sol"
    assert load_config().models.overrides.codex.relevance == "gpt-6-luna"

    assert cli.main(["models", "refresh", "--yes"]) == 0
    assert "최신" in capsys.readouterr().out


def test_cli_models_refresh_fails_without_catalog(catalog, isolated_config, capsys):
    catalog(None)
    assert cli.main(["models", "refresh", "--yes"]) == 1
    assert "카탈로그 조회 실패" in capsys.readouterr().err
    assert not isolated_config.exists()


def test_doctor_codex_models_reports_status(catalog, isolated_config) -> None:
    result = diagnose_codex_models()
    assert result.status == DiagnosticStatus.WARN
    assert "models refresh" in result.message
    assert "실행 중 자동 대체" in result.message  # gpt-5.6-terra는 카탈로그에 없음

    cli.main(["models", "refresh", "--yes"])
    assert diagnose_codex_models().status == DiagnosticStatus.OK

    catalog(None)
    assert diagnose_codex_models().status == DiagnosticStatus.UNKNOWN
