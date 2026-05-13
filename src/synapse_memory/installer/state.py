"""Installer 상태 머신.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


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
