"""doctor vault config 일관성 진단 + --fix-config 안전 가드 테스트.

B3 (eng-review 2026-05-13): silent overwrite 차단 검증.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from synapse_memory.config import SynapseConfig
from synapse_memory.doctor import (
    DiagnosticStatus,
    apply_set_config_vault,
    diagnose_vault_config_consistency,
)


def _make_vault(root: Path, name: str) -> Path:
    """가짜 Obsidian vault 디렉터리 생성 (`.obsidian/` 포함)."""
    vault = root / name
    vault.mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    return vault


def test_vault_null_with_detection_warns_and_recommends_fix(tmp_path: Path) -> None:
    """case A: config vault=None + detection 성공 → WARN + fixable."""
    home = tmp_path / "home"
    home.mkdir()
    documents = home / "Documents"
    documents.mkdir()
    vault = _make_vault(documents, "MyVault")

    result = diagnose_vault_config_consistency(None, home=home)

    assert result.status == DiagnosticStatus.WARN
    assert result.fixable is True
    assert result.fix_action_id == "set_config_vault"
    assert result.target == vault
    assert "--fix-config" in result.message


def test_vault_valid_config_no_drift_is_ok(tmp_path: Path) -> None:
    """case B: config vault 가 실제 디렉터리 → OK."""
    home = tmp_path / "home"
    home.mkdir()
    documents = home / "Documents"
    documents.mkdir()
    vault = _make_vault(documents, "MyVault")

    result = diagnose_vault_config_consistency(str(vault), home=home)

    assert result.status == DiagnosticStatus.OK
    assert result.fixable is False


def test_vault_invalid_config_with_detection_warns(tmp_path: Path) -> None:
    """case C: config vault 경로 존재 X + detection 성공 → WARN + fixable."""
    home = tmp_path / "home"
    home.mkdir()
    documents = home / "Documents"
    documents.mkdir()
    vault = _make_vault(documents, "RealVault")

    bogus = tmp_path / "does-not-exist"

    result = diagnose_vault_config_consistency(str(bogus), home=home)

    assert result.status == DiagnosticStatus.WARN
    assert result.fixable is True
    assert result.target == vault


def test_vault_null_no_detection_warns_not_fixable(tmp_path: Path) -> None:
    """case D: config null + detection 없음 → WARN, not fixable."""
    home = tmp_path / "home"
    home.mkdir()

    result = diagnose_vault_config_consistency(None, home=home)

    assert result.status == DiagnosticStatus.WARN
    assert result.fixable is False
    assert "감지 실패" in result.message or "수동 설정" in result.message


def test_vault_invalid_config_no_detection_fails(tmp_path: Path) -> None:
    """case E: config vault 경로 존재 X + detection 없음 → FAIL."""
    home = tmp_path / "home"
    home.mkdir()

    result = diagnose_vault_config_consistency("/nonexistent", home=home)

    assert result.status == DiagnosticStatus.FAIL
    assert result.fixable is False


def test_apply_set_config_vault_writes_to_config(tmp_path: Path) -> None:
    """apply_set_config_vault: 명시적 호출 시에만 config 변경 (silent overwrite 차단 검증)."""
    target = tmp_path / "vault"
    target.mkdir()

    with patch("synapse_memory.config.load_config") as mock_load, \
         patch("synapse_memory.config.save_config") as mock_save:
        mock_load.return_value = SynapseConfig(vault=None)
        result = apply_set_config_vault(target)
        assert result.status == "success"
        assert result.action_id == "set_config_vault"
        assert str(target) in result.summary
        mock_save.assert_called_once()


def test_apply_set_config_vault_preserves_old_value_in_summary(tmp_path: Path) -> None:
    """old vault 값이 summary 에 보존되어야 사용자가 변경 내용 인지 가능."""
    target = tmp_path / "new-vault"
    target.mkdir()

    with patch("synapse_memory.config.load_config") as mock_load, \
         patch("synapse_memory.config.save_config"):
        mock_load.return_value = SynapseConfig(vault="/old/path")
        result = apply_set_config_vault(target)
        assert "/old/path" in result.summary
        assert str(target) in result.summary


def test_planned_fix_actions_excludes_set_config_vault(tmp_path: Path) -> None:
    """critical safety: --fix (planned_fix_actions) 가 vault config 를 자동 변경하면 안 됨."""
    from synapse_memory.doctor import planned_fix_actions

    home = tmp_path / "home"
    home.mkdir()
    documents = home / "Documents"
    documents.mkdir()
    _make_vault(documents, "MyVault")

    vc_result = diagnose_vault_config_consistency(None, home=home)
    assert vc_result.fix_action_id == "set_config_vault"

    actions = planned_fix_actions([vc_result])
    action_ids = [a.id for a in actions]
    assert "set_config_vault" not in action_ids, (
        "vault config 변경은 --fix 가 아니라 --fix-config 명시 호출로만 가능해야 함 "
        "(eng-review A2 critical gap)"
    )
