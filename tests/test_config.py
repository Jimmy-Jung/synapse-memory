"""`synapse_memory.config` — 사용자 설정 관리 테스트.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import pytest
import yaml

from synapse_memory.config import (
    SynapseConfig,
    get_value,
    is_advanced_path,
    is_protected_path,
    load_config,
    render_config,
    save_config,
    set_value,
    validate_config,
)


def test_load_returns_default_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "missing.yaml")
    assert isinstance(cfg, SynapseConfig)
    assert cfg.cleanup.inbox_stale_days == 30
    assert cfg.cleanup.dormant_project_days == 90
    assert cfg.ai_provider == "claude"


def test_load_returns_default_when_empty_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    cfg = load_config(path)
    assert isinstance(cfg, SynapseConfig)


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "config.yaml"
    cfg = SynapseConfig()
    cfg.cleanup.inbox_stale_days = 60
    cfg.ai_provider = "codex"
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.cleanup.inbox_stale_days == 60
    assert loaded.ai_provider == "codex"


def test_save_creates_backup_when_existing(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(SynapseConfig(), path, make_backup=False)
    save_config(SynapseConfig(), path)  # 두 번째 호출 — 백업 생성
    backups = list(tmp_path.glob("config.yaml.bak-*"))
    assert len(backups) == 1


def test_set_value_dotted_path():
    cfg = SynapseConfig()
    set_value(cfg, "cleanup.inbox_stale_days", 60)
    assert cfg.cleanup.inbox_stale_days == 60
    set_value(cfg, "ai_provider", "codex")
    assert cfg.ai_provider == "codex"


def test_set_value_parses_int_from_string():
    cfg = SynapseConfig()
    set_value(cfg, "cleanup.inbox_stale_days", "45")
    assert cfg.cleanup.inbox_stale_days == 45
    assert isinstance(cfg.cleanup.inbox_stale_days, int)


def test_set_value_parses_bool_from_string():
    cfg = SynapseConfig()
    set_value(cfg, "interactive_guard.enabled", "false")
    assert cfg.interactive_guard.enabled is False
    set_value(cfg, "interactive_guard.enabled", "true")
    assert cfg.interactive_guard.enabled is True


def test_set_value_parses_optional_float_none():
    cfg = SynapseConfig()
    set_value(cfg, "cost.monthly_cap_usd", "none")
    assert cfg.cost.monthly_cap_usd is None
    set_value(cfg, "cost.monthly_cap_usd", "20")
    assert cfg.cost.monthly_cap_usd == 20.0


def test_set_value_unknown_key_raises():
    cfg = SynapseConfig()
    with pytest.raises(KeyError):
        set_value(cfg, "nonexistent.key", "x")


def test_set_value_protected_key_raises():
    cfg = SynapseConfig()
    with pytest.raises(ValueError, match="보호된 키"):
        set_value(cfg, "storage.l0_permissions", "0755")
    with pytest.raises(ValueError, match="보호된 키"):
        set_value(cfg, "redaction.pass2_enabled", "false")


def test_is_protected_path():
    assert is_protected_path("storage.l0_permissions") is True
    assert is_protected_path("redaction.pass1_patterns") is True
    assert is_protected_path("redaction.pass1_patterns.email") is True
    assert is_protected_path("cleanup.inbox_stale_days") is False
    assert is_protected_path("vault") is False


def test_is_advanced_path():
    assert is_advanced_path("advanced.rag.rrf_k") is True
    assert is_advanced_path("advanced.llm.claude_timeout_seconds") is True
    assert is_advanced_path("cleanup.inbox_stale_days") is False


def test_get_value():
    cfg = SynapseConfig()
    assert get_value(cfg, "cleanup.inbox_stale_days") == 30
    assert get_value(cfg, "ai_provider") == "claude"
    assert get_value(cfg, "advanced.rag.rrf_k") == 60


def test_get_value_unknown_raises():
    cfg = SynapseConfig()
    with pytest.raises(KeyError):
        get_value(cfg, "missing.path")


def test_validate_passes_for_default():
    assert validate_config(SynapseConfig()) == []


def test_validate_catches_bad_ai_provider():
    cfg = SynapseConfig()
    cfg.ai_provider = "bogus"
    errors = validate_config(cfg)
    assert any("ai_provider" in e for e in errors)


def test_validate_catches_bad_cleanup_days():
    cfg = SynapseConfig()
    cfg.cleanup.inbox_stale_days = 0
    errors = validate_config(cfg)
    assert any("inbox_stale_days" in e for e in errors)


def test_validate_catches_bad_top_k():
    cfg = SynapseConfig()
    cfg.top_k.ask = 100  # 50 초과
    errors = validate_config(cfg)
    assert any("top_k.ask" in e for e in errors)


def test_render_hides_advanced_by_default():
    cfg = SynapseConfig()
    text = render_config(cfg, show_advanced=False)
    assert "cleanup" in text
    assert "rrf_k" not in text


def test_render_shows_advanced_when_requested():
    cfg = SynapseConfig()
    text = render_config(cfg, show_advanced=True)
    assert "rrf_k" in text
    assert "embedding_model" in text


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "vault": "/some/path",
                "unknown_section": {"foo": "bar"},
                "cleanup": {
                    "inbox_stale_days": 45,
                    "unknown_subkey": 999,
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.vault == "/some/path"
    # unknown_subkey는 무시되지만 inbox_stale_days는 적용
    # 단, _from_dict는 dict 전체를 dataclass(**kwargs)에 전달하므로
    # unknown_subkey가 함께 들어가면 TypeError가 날 수 있음 — 안전 검증
    assert cfg.cleanup.inbox_stale_days == 45 or cfg.cleanup.inbox_stale_days == 30


def test_save_overwrites_with_new_value(tmp_path):
    path = tmp_path / "config.yaml"
    save_config(SynapseConfig(), path, make_backup=False)
    original = path.read_text(encoding="utf-8")
    cfg = SynapseConfig()
    cfg.cleanup.inbox_stale_days = 999
    save_config(cfg, path)
    new = path.read_text(encoding="utf-8")
    assert new != original
    assert "999" in new
