"""Installer 상태 머신.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse_memory.installer.logging import sanitize_log_message


class InstallerState(StrEnum):
    PLANNED = "planned"
    CONSENTED = "consented"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class StepKind(StrEnum):
    DETECT = "detect"
    INSTALL = "install"
    CONFIGURE = "configure"
    VERIFY = "verify"
    ROLLBACK = "rollback"


@dataclass(frozen=True)
class ConsentReceipt:
    is_approved: bool
    approved_at: dt.datetime | None
    prompt_version: str
    scope: tuple[str, ...]
    exclusions: tuple[str, ...] = (
        "reflect --apply",
        "archive --apply",
        "운영 단계 메모리 쓰기",
    )

    @classmethod
    def approve(
        cls,
        *,
        scope: tuple[str, ...],
        prompt_version: str = "installer-consent-v1",
    ) -> ConsentReceipt:
        return cls(
            is_approved=True,
            approved_at=dt.datetime.now(dt.UTC),
            prompt_version=prompt_version,
            scope=scope,
        )

    @classmethod
    def denied(
        cls,
        *,
        prompt_version: str = "installer-consent-v1",
    ) -> ConsentReceipt:
        return cls(
            is_approved=False,
            approved_at=None,
            prompt_version=prompt_version,
            scope=(),
        )

    @property
    def approved(self) -> bool:
        return self.is_approved


@dataclass(frozen=True)
class InstallerStep:
    id: str
    label: str
    kind: StepKind
    apply_mode: str = "read_only"
    requires_consent: bool = False
    rollback_supported: bool = False


@dataclass(frozen=True)
class InstallerStepResult:
    step_id: str
    status: str
    started_at: dt.datetime
    elapsed_ms: int = 0
    summary: str = ""
    remediation: str = ""


@dataclass
class InstallerSession:
    session_id: str
    started_at: dt.datetime
    log_path: Path
    state: InstallerState = InstallerState.PLANNED
    consent: ConsentReceipt = field(default_factory=ConsentReceipt.denied)
    selected_vault: Path | None = None
    completed_at: dt.datetime | None = None
    rollback_path: Path | None = None
    steps: list[InstallerStepResult] = field(default_factory=list)

    @classmethod
    def start(cls, *, log_path: Path) -> InstallerSession:
        return cls(
            session_id=uuid4().hex,
            started_at=dt.datetime.now(dt.UTC),
            log_path=log_path.expanduser(),
        )

    def with_consent(self, consent: ConsentReceipt) -> InstallerSession:
        self.consent = consent
        self.state = InstallerState.CONSENTED if consent.approved else InstallerState.CANCELLED
        return self

    def record_step(
        self,
        step: InstallerStep,
        *,
        status: str = "success",
        summary: str = "",
        remediation: str = "",
    ) -> InstallerStepResult:
        started_at = dt.datetime.now(dt.UTC)
        if step.requires_consent and not self.consent.approved:
            result = InstallerStepResult(
                step_id=step.id,
                status="failed",
                started_at=started_at,
                summary=f"{step.label}: 설치 동의가 필요합니다",
                remediation="Installer consent dialog를 승인한 뒤 다시 실행하세요.",
            )
            self.steps.append(result)
            self.state = InstallerState.FAILED
            return result

        result = InstallerStepResult(
            step_id=step.id,
            status=status,
            started_at=started_at,
            summary=summary,
            remediation=remediation,
        )
        self.steps.append(result)
        if status == "failed":
            self.state = InstallerState.FAILED
        elif self.state in (InstallerState.PLANNED, InstallerState.CONSENTED):
            self.state = InstallerState.RUNNING
        return result


@dataclass(frozen=True)
class InstallerManifestStep:
    step_id: str
    status: str
    phase: str
    summary: str
    recorded_at: str


@dataclass(frozen=True)
class InstallerManifest:
    version: int
    state: str
    dry_run: bool
    started_at: str
    updated_at: str
    log_path: str
    state_path: str
    steps: list[InstallerManifestStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "state": self.state,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "log_path": self.log_path,
            "state_path": self.state_path,
            "steps": [asdict(step) for step in self.steps],
        }


def load_manifest(path: Path) -> InstallerManifest | None:
    """Read an installer state manifest. Invalid or missing files return None."""
    try:
        raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    steps_raw = raw.get("steps", [])
    if not isinstance(steps_raw, list):
        steps_raw = []
    steps: list[InstallerManifestStep] = []
    for item in steps_raw:
        if not isinstance(item, dict):
            continue
        try:
            steps.append(
                InstallerManifestStep(
                    step_id=str(item["step_id"]),
                    status=str(item["status"]),
                    phase=str(item["phase"]),
                    summary=str(item.get("summary", "")),
                    recorded_at=str(item["recorded_at"]),
                )
            )
        except KeyError:
            continue
    try:
        return InstallerManifest(
            version=int(raw.get("version", 1)),
            state=str(raw.get("state", "running")),
            dry_run=bool(raw.get("dry_run", True)),
            started_at=str(raw["started_at"]),
            updated_at=str(raw["updated_at"]),
            log_path=str(raw.get("log_path", "")),
            state_path=str(raw.get("state_path", path.expanduser())),
            steps=steps,
        )
    except KeyError:
        return None


def append_manifest_step(
    path: Path,
    *,
    log_path: Path,
    dry_run: bool,
    step_id: str,
    status: str,
    summary: str,
    phase: str | None = None,
    clock: Callable[[], str] | None = None,
) -> InstallerManifest:
    """Append one installer step to a JSON state manifest using atomic write."""
    resolved = path.expanduser()
    now = (clock or _utc_now_iso)()
    previous = load_manifest(resolved)
    steps = list(previous.steps) if previous is not None else []
    steps.append(
        InstallerManifestStep(
            step_id=step_id,
            status=status,
            phase=phase or infer_manifest_phase(step_id=step_id, status=status),
            summary=sanitize_log_message(summary),
            recorded_at=now,
        )
    )
    manifest = InstallerManifest(
        version=1,
        state=_manifest_state_for_step(
            step_id=step_id,
            status=status,
            previous_state=previous.state if previous is not None else None,
        ),
        dry_run=dry_run,
        started_at=previous.started_at if previous is not None else now,
        updated_at=now,
        log_path=str(log_path.expanduser()),
        state_path=str(resolved),
        steps=steps,
    )
    _write_manifest_atomic(resolved, manifest)
    return manifest


def infer_manifest_phase(*, step_id: str, status: str) -> str:
    if status == "preview":
        return "preview"
    if step_id.startswith(("verify_", "validate_")):
        return "verify"
    if step_id.startswith("detect_") or step_id in {"platform"}:
        return "detect"
    if step_id in {"start", "consent", "complete"}:
        return "lifecycle"
    return "apply"


def _manifest_state_for_step(
    *,
    step_id: str,
    status: str,
    previous_state: str | None = None,
) -> str:
    if previous_state in {"failed", "cancelled"} and status != "success":
        return previous_state
    if status == "failed":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if previous_state in {"failed", "cancelled"}:
        return previous_state
    if step_id == "complete" and status == "success":
        return "succeeded"
    return "running"


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _write_manifest_atomic(path: Path, manifest: InstallerManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
