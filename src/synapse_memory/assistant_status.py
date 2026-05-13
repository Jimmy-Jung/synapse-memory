"""Assistant 모드용 read-only 진단 묶음.

`/sm:assistant` 슬래시 명령이 vault 상태를 한 번에 읽어
"오늘 추천 작업"을 제안할 수 있도록 가벼운 read-only API를 제공한다.

수집 항목:
- environment: doctor private-permissions 결과 (apfel 등 외부 의존성은 호출하지 않음 — fast read-only)
- inbox_pending: MemoryInbox 검토 대기 파일 수와 가장 최근 경로
- draft_cards: status=draft인 카드 수 (project, company 각각)
- empty_companies: positions가 비어 있는 회사 카드 수 (이력서 매칭에 영향)
- last_daily: 마지막 daily 실행 시각·상태
- counts: 전체 카드 수 / vault 경로 등

JSON 또는 사람용 텍스트로 렌더링한다. 슬래시 명령 안에서 호출되므로
어떤 단계가 실패해도 best-effort로 계속 진행한다 (예외 전파 X).

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from synapse_memory.cards.company import list_company_cards
from synapse_memory.cards.project import list_project_cards
from synapse_memory.cleanup import scan_cleanup_candidates
from synapse_memory.config import get_config
from synapse_memory.doctor import DiagnosticStatus, diagnose_private_permissions
from synapse_memory.status import read_status

PRIVATE_ROOT = Path.home() / ".synapse" / "private"


@dataclass(frozen=True)
class AssistantStatus:
    """비서 모드 read-only 스냅샷."""

    vault_path: str | None
    project_card_count: int
    company_card_count: int
    draft_project_count: int
    draft_company_count: int
    empty_company_count: int
    inbox_pending_count: int
    inbox_pending_latest: str | None
    last_daily_at: str | None
    last_daily_state: str | None
    doctor_ok: bool
    doctor_issues: list[str] = field(default_factory=list)
    cleanup_candidate_count: int = 0
    cleanup_by_kind: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def resolve_vault_path() -> Path | None:
    """vault 경로 해결 — fallback 체인.

    우선순위:
    1. ``SYNAPSE_OBSIDIAN_VAULT`` 환경변수
    2. ``~/.synapse/config.yaml`` 의 ``vault`` 키
    3. ``~/Library/Mobile Documents/iCloud~md~obsidian/Documents`` (기본 iCloud Obsidian)

    daily/config 파이프라인과 동일한 소스를 참조해 entrypoint 간 불일치를 방지한다.
    어떤 단계도 해결하지 못하면 ``None`` 반환.
    """
    raw = os.environ.get("SYNAPSE_OBSIDIAN_VAULT")
    if raw:
        return Path(raw).expanduser()

    try:
        from synapse_memory.config import load_config

        cfg_vault = load_config().vault
    except Exception:
        cfg_vault = None
    if cfg_vault:
        return Path(cfg_vault).expanduser()

    try:
        from synapse_memory.collectors.obsidian.mirror import DEFAULT_VAULT_PATH

        if DEFAULT_VAULT_PATH.exists():
            return DEFAULT_VAULT_PATH
    except Exception:
        pass

    return None


def gather_status(*, vault_path: Path | None = None) -> AssistantStatus:
    """vault·doctor·inbox·last-daily 진단을 한 번에 묶어 반환."""
    if vault_path is None:
        vault_path = resolve_vault_path()

    project_count = 0
    draft_projects = 0
    company_count = 0
    draft_companies = 0
    empty_companies = 0
    inbox_count = 0
    inbox_latest: str | None = None

    if vault_path is not None and vault_path.exists():
        try:
            projects = list_project_cards(vault_path=vault_path)
            project_count = len(projects)
            draft_projects = sum(
                1 for c in projects if (c.status or "").lower() == "draft"
            )
        except Exception:
            pass

        try:
            companies = list_company_cards(vault_path=vault_path)
            company_count = len(companies)
            draft_companies = sum(
                1 for c in companies if (c.status or "").lower() == "draft"
            )
            empty_companies = sum(1 for c in companies if not c.positions)
        except Exception:
            pass

        inbox_dir = vault_path / get_config().vault_folders.system.ai.memory_inbox
        if inbox_dir.exists():
            files = sorted(inbox_dir.glob("Profile-*.md"), reverse=True)
            inbox_count = len(files)
            if files:
                inbox_latest = str(files[0])

    doctor_issues: list[str] = []
    doctor_ok = True
    try:
        result = diagnose_private_permissions(PRIVATE_ROOT)
        if result.status != DiagnosticStatus.OK:
            doctor_ok = False
            doctor_issues.append(result.message)
    except Exception as e:
        doctor_ok = False
        doctor_issues.append(f"diagnose 실패: {e}")

    last_status = read_status()
    last_daily_at = last_status.updated_at if last_status else None
    last_daily_state = last_status.state if last_status else None

    cleanup_count = 0
    cleanup_by_kind: dict[str, int] = {}
    if vault_path is not None and vault_path.exists():
        try:
            plan = scan_cleanup_candidates(vault_path)
            cleanup_count = len(plan.candidates)
            cleanup_by_kind = {k: len(v) for k, v in plan.by_kind().items()}
        except Exception:
            pass

    return AssistantStatus(
        vault_path=str(vault_path) if vault_path else None,
        project_card_count=project_count,
        company_card_count=company_count,
        draft_project_count=draft_projects,
        draft_company_count=draft_companies,
        empty_company_count=empty_companies,
        inbox_pending_count=inbox_count,
        inbox_pending_latest=inbox_latest,
        last_daily_at=last_daily_at,
        last_daily_state=last_daily_state,
        doctor_ok=doctor_ok,
        doctor_issues=doctor_issues,
        cleanup_candidate_count=cleanup_count,
        cleanup_by_kind=cleanup_by_kind,
    )


def recommend_actions(status: AssistantStatus) -> list[str]:
    """status 기반 우선순위 추천 작업 목록.

    규칙(상위 우선):
    1. doctor 문제 → /sm:fix
    2. vault 미설정 → SYNAPSE_OBSIDIAN_VAULT 안내 (이후 추천 중단)
    3. MemoryInbox 검토 대기 ≥ 1 → 검토 권유
    4. status=draft 카드 ≥ 1 → 카드 검토 + active 승격 권유
    5. positions 비어 있는 회사 카드 ≥ 1 → 키워드 보강 권유
    6. 마지막 daily 기록 없거나 마지막 state != "done" → /sm:daily 권유
    7. 그 외 → 자유 질문 안내
    """
    recs: list[str] = []

    if not status.doctor_ok:
        recs.append("환경 문제 자동 복구 — `/sm:fix` (안전한 항목만)")

    if not status.vault_path:
        recs.append(
            "Obsidian vault 경로 설정 — "
            "`synapse-memory config set vault '<vault 경로>'` 또는 "
            "`export SYNAPSE_OBSIDIAN_VAULT='<vault 경로>'`"
        )
        return recs

    if status.inbox_pending_count > 0:
        latest = status.inbox_pending_latest or ""
        recs.append(
            f"MemoryInbox 검토 ({status.inbox_pending_count}개 대기) — "
            f"Obsidian에서 {latest or 'Profile-*.md'} 열고 맞는 항목을 "
            f"Profile.md / DecisionPatterns.md로 옮기기"
        )

    draft_total = status.draft_project_count + status.draft_company_count
    if draft_total > 0:
        recs.append(
            f"draft 카드 검토 + 승격 ({draft_total}장) — Obsidian에서 frontmatter "
            f"`status: draft` → `active`"
        )

    if status.empty_company_count > 0:
        recs.append(
            f"키워드 비어 있는 회사 카드 보강 ({status.empty_company_count}장) — "
            f"`/sm:resume` 매칭 정확도가 올라감"
        )

    if status.last_daily_at is None or status.last_daily_state != "done":
        recs.append("일일 정리 실행 — `/sm:daily` (1~3분)")

    if status.cleanup_candidate_count > 0:
        kinds = ", ".join(
            f"{k}({n})" for k, n in sorted(status.cleanup_by_kind.items())
        )
        recs.append(
            f"vault 청소 후보 {status.cleanup_candidate_count}건 — `/sm:cleanup` "
            f"({kinds})"
        )

    if not recs:
        recs.append(
            "오늘 자유롭게 질문 — `/sm:ask \"...\"` 또는 `/sm:recall <주제>`"
        )

    return recs


def render_status(status: AssistantStatus) -> str:
    """사람용 한 페이지 요약."""
    lines: list[str] = []
    if not status.vault_path:
        lines.append("⚠ vault 경로 미설정 (SYNAPSE_OBSIDIAN_VAULT)")
    else:
        lines.append(f"vault: {status.vault_path}")
    lines.append(
        f"카드: project={status.project_card_count} "
        f"(draft {status.draft_project_count}) / "
        f"company={status.company_card_count} "
        f"(draft {status.draft_company_count})"
    )
    if status.empty_company_count > 0:
        lines.append(
            f"키워드(positions) 비어 있는 회사 카드: {status.empty_company_count}"
        )
    lines.append(f"MemoryInbox 검토 대기: {status.inbox_pending_count}")
    if status.inbox_pending_latest:
        lines.append(f"  최근: {status.inbox_pending_latest}")
    if status.last_daily_at:
        lines.append(
            f"마지막 daily: {status.last_daily_at} ({status.last_daily_state})"
        )
    else:
        lines.append("마지막 daily: 실행 기록 없음")
    if status.doctor_ok:
        lines.append("doctor: ✓ OK (private permissions)")
    else:
        lines.append("doctor: ⚠ 문제 있음")
        for issue in status.doctor_issues:
            lines.append(f"  - {issue}")

    if status.cleanup_candidate_count > 0:
        kinds = ", ".join(
            f"{k}({n})" for k, n in sorted(status.cleanup_by_kind.items())
        )
        lines.append(
            f"vault 청소 후보: {status.cleanup_candidate_count}건 — {kinds}"
        )

    suggestions = recommend_actions(status)
    if suggestions:
        lines.append("")
        lines.append("추천 작업 (우선순위 순):")
        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s}")

    return "\n".join(lines)
