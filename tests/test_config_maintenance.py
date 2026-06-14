"""maintenance + vault_folders.wiki 설정 기본값/override 검증."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.config import get_config


def test_maintenance_defaults() -> None:
    cfg = get_config(refresh=True)
    assert cfg.maintenance.engine == "claude"
    assert cfg.maintenance.idle_minutes == 3


def test_wiki_folder_defaults() -> None:
    cfg = get_config(refresh=True)
    w = cfg.vault_folders.wiki
    assert w.projects == "Entities/Projects"
    assert w.companies == "Entities/Companies"
    assert w.people == "Entities/People"
    assert w.concepts == "Concepts"
    assert w.profile == "Profile"
    assert w.insights == "Insights"


def test_maintenance_override_from_yaml(tmp_path: Path, monkeypatch) -> None:
    # get_config는 모듈 레벨 DEFAULT_CONFIG_PATH를 직접 읽으므로
    # (SYNAPSE_CONFIG_PATH env var 미지원) 해당 상수를 monkeypatch한다.
    import synapse_memory.config as config_module

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "maintenance:\n  engine: codex\n  idle_minutes: 5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", cfg_file)
    cfg = get_config(refresh=True)
    assert cfg.maintenance.engine == "codex"
    assert cfg.maintenance.idle_minutes == 5
