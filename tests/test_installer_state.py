"""Installer 상태 모델 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.installer.logging import InstallerLogger, sanitize_log_message
from synapse_memory.installer.state import (
    ConsentReceipt,
    InstallerSession,
    InstallerState,
    InstallerStep,
    StepKind,
)


def test_installer_session_requires_consent_before_apply(tmp_path: Path) -> None:
    session = InstallerSession.start(log_path=tmp_path / "installer.log")
    step = InstallerStep(
        id="install_apfel",
        label="apfel 설치",
        kind=StepKind.INSTALL,
        apply_mode="apply",
        requires_consent=True,
    )

    result = session.record_step(step)

    assert result.status == "failed"
    assert "동의" in result.summary
    assert session.state == InstallerState.FAILED


def test_installer_session_records_consented_apply_step(tmp_path: Path) -> None:
    session = InstallerSession.start(log_path=tmp_path / "installer.log")
    session = session.with_consent(ConsentReceipt.approve(scope=("bootstrap",)))
    step = InstallerStep(
        id="bootstrap_runtime",
        label="Runtime bootstrap",
        kind=StepKind.CONFIGURE,
        apply_mode="apply",
        requires_consent=True,
    )

    result = session.record_step(step, status="success", summary="runtime_ready=true")

    assert result.status == "success"
    assert session.state == InstallerState.RUNNING
    assert session.steps[-1].step_id == "bootstrap_runtime"


def test_installer_logger_sanitizes_raw_content(tmp_path: Path) -> None:
    logger = InstallerLogger(tmp_path / "installer.log")

    logger.write_step("collect", "success", "raw_content=secret token=abc123")

    text = (tmp_path / "installer.log").read_text(encoding="utf-8")
    assert "secret" not in text
    assert "token=abc123" not in text
    assert "[redacted]" in text


def test_sanitize_log_message_redacts_prompt_and_response() -> None:
    text = sanitize_log_message("prompt=hello response=world oauth=private")

    assert text == "prompt=[redacted] response=[redacted] oauth=[redacted]"
