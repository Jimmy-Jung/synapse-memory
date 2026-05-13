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
    append_manifest_step,
    infer_manifest_phase,
    load_manifest,
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


def test_manifest_records_steps_atomically(tmp_path: Path) -> None:
    manifest_path = tmp_path / "installer.state.json"
    log_path = tmp_path / "installer.log"

    append_manifest_step(
        manifest_path,
        log_path=log_path,
        dry_run=True,
        step_id="start",
        status="success",
        summary="log=/tmp/installer.log",
        clock=lambda: "2026-05-13T00:00:00+00:00",
    )
    manifest = append_manifest_step(
        manifest_path,
        log_path=log_path,
        dry_run=True,
        step_id="install_apfel",
        status="preview",
        summary="would install apfel token=abc123",
        clock=lambda: "2026-05-13T00:00:01+00:00",
    )

    reloaded = load_manifest(manifest_path)

    assert reloaded is not None
    assert manifest.state == "running"
    assert reloaded.dry_run is True
    assert reloaded.log_path == str(log_path)
    assert [step.step_id for step in reloaded.steps] == ["start", "install_apfel"]
    assert reloaded.steps[-1].phase == "preview"
    assert "token=abc123" not in reloaded.steps[-1].summary
    assert "token=[redacted]" in reloaded.steps[-1].summary


def test_manifest_marks_complete_and_failed_states(tmp_path: Path) -> None:
    manifest_path = tmp_path / "installer.state.json"
    log_path = tmp_path / "installer.log"

    failed = append_manifest_step(
        manifest_path,
        log_path=log_path,
        dry_run=False,
        step_id="verify_codex_plugin",
        status="failed",
        summary="prompt_visible=false",
    )
    assert failed.state == "failed"

    complete_path = tmp_path / "complete.state.json"
    complete = append_manifest_step(
        complete_path,
        log_path=log_path,
        dry_run=False,
        step_id="complete",
        status="success",
        summary="dry_run=0",
    )
    assert complete.state == "succeeded"


def test_manifest_preserves_prior_failure_on_complete(tmp_path: Path) -> None:
    manifest_path = tmp_path / "installer.state.json"
    log_path = tmp_path / "installer.log"

    append_manifest_step(
        manifest_path,
        log_path=log_path,
        dry_run=False,
        step_id="detect_brew",
        status="failed",
        summary="brew not found",
    )
    complete = append_manifest_step(
        manifest_path,
        log_path=log_path,
        dry_run=False,
        step_id="complete",
        status="success",
        summary="dry_run=0",
    )

    assert complete.state == "failed"
    assert [step.step_id for step in complete.steps] == ["detect_brew", "complete"]


def test_manifest_phase_inference() -> None:
    assert infer_manifest_phase(step_id="install_apfel", status="preview") == "preview"
    assert infer_manifest_phase(step_id="verify_codex_plugin", status="success") == "verify"
    assert infer_manifest_phase(step_id="detect_brew", status="success") == "detect"
    assert infer_manifest_phase(step_id="bootstrap_runtime", status="success") == "apply"
