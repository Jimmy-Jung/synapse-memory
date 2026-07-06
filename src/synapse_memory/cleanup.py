"""vault 청소 도우미 — 오래된·휴면·빈 자료를 archive 폴더로 *이동*.

핵심 원칙:
- 영구 삭제 0건. 모든 이동은 설정된 archive 폴더의 ``_cleanup-YYYY-MM-DD/``로.
- 기본은 ``dry_run=True``. ``apply=True``를 명시해야 실제 이동.
- 모든 이동은 설정된 CleanupReports 폴더에 매니페스트로 기록.
- 진실원본(`Profile.md`, `DecisionPatterns.md`, `recipes/` 등)은 절대 건드리지 않음.
- frontmatter ``pinned: true`` 또는 ``cleanup: skip``이 있으면 건너뜀.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import datetime
import json
import shutil
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from synapse_memory.config import VaultFoldersConfig

DEFAULT_INBOX_STALE_DAYS = 30
DEFAULT_DORMANT_PROJECT_DAYS = 90
DEFAULT_OLD_RESUME_DAYS = 90
DEFAULT_STALE_MEMORY_INBOX_DAYS = 60
DEFAULT_OLD_DAILY_REPORTS_DAYS = 90


class CleanupKind(StrEnum):
    INBOX_STALE = "inbox_stale"
    DORMANT_PROJECT = "dormant_project"
    OLD_RESUME = "old_resume"
    STALE_MEMORY_INBOX = "stale_memory_inbox"
    EMPTY_CARD = "empty_card"
    OLD_DAILY_REPORT = "old_daily_report"
    EMPTY_FOLDER = "empty_folder"


@dataclass(frozen=True)
class CleanupCandidate:
    kind: CleanupKind
    source_path: str
    target_path: str
    reason: str
    age_days: int | None = None
    size_bytes: int | None = None


@dataclass(frozen=True)
class CleanupResult:
    candidate: CleanupCandidate
    status: str  # "moved" | "skipped" | "failed" | "dry_run"
    detail: str = ""


@dataclass(frozen=True)
class CleanupPlan:
    vault_path: str
    scanned_at: str
    candidates: list[CleanupCandidate] = field(default_factory=list)

    def by_kind(self) -> dict[str, list[CleanupCandidate]]:
        out: dict[str, list[CleanupCandidate]] = {}
        for c in self.candidates:
            out.setdefault(c.kind.value, []).append(c)
        return out

    def to_json(self) -> str:
        payload = {
            "vault_path": self.vault_path,
            "scanned_at": self.scanned_at,
            "candidates": [{**asdict(c), "kind": c.kind.value} for c in self.candidates],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def _file_age_days(path: Path, now: datetime.datetime) -> int:
    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.UTC)
    return (now - mtime).days


def _read_frontmatter(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _relative_config_path(value: str, *, key: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{key}는 vault root 기준 안전한 상대 경로여야 함: {value!r}")
    return path


def _vault_path(vault: Path, rel_path: str, *, key: str) -> Path:
    return vault / _relative_config_path(rel_path, key=key)


def _is_protected(rel_path: Path, folders: VaultFoldersConfig) -> bool:
    rel = str(rel_path).replace("\\", "/")
    protected_files = {
        folders.system.ai.profile,
        folders.system.ai.decision_patterns,
    }
    protected_dirs = {
        "Profile",
        folders.system.ai.recipes,
    }
    if rel in protected_files:
        return True
    return any(rel.startswith(d + "/") for d in protected_dirs)


def _has_skip_marker(fm: dict[str, Any] | None) -> bool:
    if not fm:
        return False
    if fm.get("pinned") is True:
        return True
    cleanup = fm.get("cleanup")
    return isinstance(cleanup, str) and cleanup.lower() == "skip"


def _archive_target(
    vault: Path,
    source: Path,
    *,
    archive_date: str,
    folders: VaultFoldersConfig,
) -> Path:
    archive_root = _vault_path(vault, folders.archive, key="vault_folders.archive")
    archive_root = archive_root / f"_cleanup-{archive_date}"
    try:
        rel = source.relative_to(vault)
    except ValueError:
        rel = Path(source.name)
    return archive_root / rel


def _is_card_empty(fm: dict[str, Any] | None) -> bool:
    if not fm:
        return False
    status = str(fm.get("status") or "").lower()
    if status not in {"draft", ""}:
        return False
    if "positions" in fm and fm.get("positions"):
        return False
    fields = ("keywords", "stack", "metrics", "domains")
    return not any(fm.get(f) for f in fields)


def _scan_inbox_stale(
    vault: Path,
    *,
    threshold_days: int,
    archive_date: str,
    now: datetime.datetime,
    folders: VaultFoldersConfig,
) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    inbox = _vault_path(vault, folders.inbox, key="vault_folders.inbox")
    if not inbox.is_dir():
        return out
    for p in inbox.rglob("*.md"):
        if not p.is_file():
            continue
        if _has_skip_marker(_read_frontmatter(p)):
            continue
        age = _file_age_days(p, now)
        if age < threshold_days:
            continue
        target = _archive_target(vault, p, archive_date=archive_date, folders=folders)
        out.append(
            CleanupCandidate(
                kind=CleanupKind.INBOX_STALE,
                source_path=str(p),
                target_path=str(target),
                reason=f"{folders.inbox}에서 {age}일 미정리",
                age_days=age,
                size_bytes=p.stat().st_size,
            )
        )
    return out


def _scan_dormant_projects(
    vault: Path,
    *,
    threshold_days: int,
    archive_date: str,
    now: datetime.datetime,
    folders: VaultFoldersConfig,
) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    active = _vault_path(vault, folders.active, key="vault_folders.active")
    if not active.is_dir():
        return out
    for company in active.iterdir():
        if not company.is_dir():
            continue
        for project in company.iterdir():
            if not project.is_dir():
                continue
            files = [p for p in project.rglob("*") if p.is_file()]
            if not files:
                continue
            md_files = [f for f in files if f.suffix == ".md"]
            if any(_has_skip_marker(_read_frontmatter(f)) for f in md_files):
                continue
            max_age = max(_file_age_days(f, now) for f in files)
            if max_age < threshold_days:
                continue
            target = _archive_target(vault, project, archive_date=archive_date, folders=folders)
            out.append(
                CleanupCandidate(
                    kind=CleanupKind.DORMANT_PROJECT,
                    source_path=str(project),
                    target_path=str(target),
                    reason=f"{max_age}일간 변경 없는 프로젝트 폴더",
                    age_days=max_age,
                    size_bytes=sum(f.stat().st_size for f in files),
                )
            )
    return out


def _scan_old_resume_drafts(
    vault: Path,
    *,
    threshold_days: int,
    archive_date: str,
    now: datetime.datetime,
    folders: VaultFoldersConfig,
) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    drafts = _vault_path(vault, folders.creative.drafts, key="vault_folders.creative.drafts")
    if not drafts.is_dir():
        return out
    for p in drafts.glob("Resume - *.md"):
        if _has_skip_marker(_read_frontmatter(p)):
            continue
        age = _file_age_days(p, now)
        if age < threshold_days:
            continue
        target = _archive_target(vault, p, archive_date=archive_date, folders=folders)
        out.append(
            CleanupCandidate(
                kind=CleanupKind.OLD_RESUME,
                source_path=str(p),
                target_path=str(target),
                reason=f"이력서 초안 {age}일 경과",
                age_days=age,
                size_bytes=p.stat().st_size,
            )
        )
    return out


def _scan_stale_memory_inbox(
    vault: Path,
    *,
    threshold_days: int,
    archive_date: str,
    now: datetime.datetime,
    folders: VaultFoldersConfig,
) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    inbox = _vault_path(
        vault,
        folders.system.ai.memory_inbox,
        key="vault_folders.system.ai.memory_inbox",
    )
    if not inbox.is_dir():
        return out
    for p in inbox.glob("Profile-*.md"):
        if _has_skip_marker(_read_frontmatter(p)):
            continue
        age = _file_age_days(p, now)
        if age < threshold_days:
            continue
        target = _archive_target(vault, p, archive_date=archive_date, folders=folders)
        out.append(
            CleanupCandidate(
                kind=CleanupKind.STALE_MEMORY_INBOX,
                source_path=str(p),
                target_path=str(target),
                reason=f"MemoryInbox 후보 {age}일간 옮겨지지 않음",
                age_days=age,
                size_bytes=p.stat().st_size,
            )
        )
    return out


def _scan_empty_cards(
    vault: Path, *, archive_date: str, folders: VaultFoldersConfig
) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    card_dirs = (
        ("vault_folders.wiki.projects", folders.wiki.projects),
        ("vault_folders.wiki.companies", folders.wiki.companies),
    )
    for key, sub in card_dirs:
        d = _vault_path(vault, sub, key=key)
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            fm = _read_frontmatter(p)
            if _has_skip_marker(fm):
                continue
            if not _is_card_empty(fm):
                continue
            target = _archive_target(vault, p, archive_date=archive_date, folders=folders)
            out.append(
                CleanupCandidate(
                    kind=CleanupKind.EMPTY_CARD,
                    source_path=str(p),
                    target_path=str(target),
                    reason="빈 draft 카드 (positions/keywords/stack/metrics 모두 비어 있음)",
                    age_days=None,
                    size_bytes=p.stat().st_size,
                )
            )
    return out


def _scan_old_daily_reports(
    vault: Path,
    *,
    threshold_days: int,
    archive_date: str,
    now: datetime.datetime,
    folders: VaultFoldersConfig,
) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    reports = _vault_path(
        vault,
        folders.system.ai.daily_reports,
        key="vault_folders.system.ai.daily_reports",
    )
    if not reports.is_dir():
        return out
    for p in reports.glob("*.md"):
        age = _file_age_days(p, now)
        if age < threshold_days:
            continue
        target = _archive_target(vault, p, archive_date=archive_date, folders=folders)
        out.append(
            CleanupCandidate(
                kind=CleanupKind.OLD_DAILY_REPORT,
                source_path=str(p),
                target_path=str(target),
                reason=f"DailyReport {age}일 경과",
                age_days=age,
                size_bytes=p.stat().st_size,
            )
        )
    return out


def _scan_empty_folders(vault: Path, *, folders: VaultFoldersConfig) -> list[CleanupCandidate]:
    out: list[CleanupCandidate] = []
    skip_top = {
        _relative_config_path(folders.archive, key="vault_folders.archive").parts[0],
        _relative_config_path(folders.system.root, key="vault_folders.system.root").parts[0],
        _relative_config_path(folders.wiki.projects, key="vault_folders.wiki.projects").parts[0],
        _relative_config_path(folders.wiki.concepts, key="vault_folders.wiki.concepts").parts[0],
        _relative_config_path(folders.wiki.profile, key="vault_folders.wiki.profile").parts[0],
        _relative_config_path(folders.wiki.insights, key="vault_folders.wiki.insights").parts[0],
    }
    for top in vault.iterdir():
        if not top.is_dir() or top.name.startswith(".") or top.name in skip_top:
            continue
        for sub in top.rglob("*"):
            if not sub.is_dir():
                continue
            try:
                rel = sub.relative_to(vault)
            except ValueError:
                continue
            if _is_protected(rel, folders):
                continue
            if any(sub.iterdir()):
                continue
            out.append(
                CleanupCandidate(
                    kind=CleanupKind.EMPTY_FOLDER,
                    source_path=str(sub),
                    target_path="(폴더 제거)",
                    reason="빈 폴더",
                    age_days=None,
                    size_bytes=0,
                )
            )
    return out


def scan_cleanup_candidates(
    vault: Path,
    *,
    now: datetime.datetime | None = None,
    inbox_stale_days: int | None = None,
    dormant_project_days: int | None = None,
    old_resume_days: int | None = None,
    stale_memory_inbox_days: int | None = None,
    old_daily_reports_days: int | None = None,
    folders: VaultFoldersConfig | None = None,
) -> CleanupPlan:
    """vault를 read-only로 스캔하여 청소 후보 목록 반환.

    임계값 None → ``~/.synapse/config.yaml``의 ``cleanup.*`` 사용.
    config 파일이 없으면 모듈 default(30/90/90/60/90)로 폴백.
    """
    from synapse_memory.config import get_config

    cfg = get_config()
    folders = folders or cfg.vault_folders
    inbox_stale_days = (
        inbox_stale_days if inbox_stale_days is not None else cfg.cleanup.inbox_stale_days
    )
    dormant_project_days = (
        dormant_project_days
        if dormant_project_days is not None
        else cfg.cleanup.dormant_project_days
    )
    old_resume_days = (
        old_resume_days if old_resume_days is not None else cfg.cleanup.old_resume_days
    )
    stale_memory_inbox_days = (
        stale_memory_inbox_days
        if stale_memory_inbox_days is not None
        else cfg.cleanup.stale_memory_inbox_days
    )
    old_daily_reports_days = (
        old_daily_reports_days
        if old_daily_reports_days is not None
        else cfg.cleanup.old_daily_reports_days
    )

    now = now or datetime.datetime.now(datetime.UTC)
    archive_date = now.strftime("%Y-%m-%d")

    candidates: list[CleanupCandidate] = []
    candidates += _scan_inbox_stale(
        vault,
        threshold_days=inbox_stale_days,
        archive_date=archive_date,
        now=now,
        folders=folders,
    )
    candidates += _scan_dormant_projects(
        vault,
        threshold_days=dormant_project_days,
        archive_date=archive_date,
        now=now,
        folders=folders,
    )
    candidates += _scan_old_resume_drafts(
        vault,
        threshold_days=old_resume_days,
        archive_date=archive_date,
        now=now,
        folders=folders,
    )
    candidates += _scan_stale_memory_inbox(
        vault,
        threshold_days=stale_memory_inbox_days,
        archive_date=archive_date,
        now=now,
        folders=folders,
    )
    candidates += _scan_empty_cards(vault, archive_date=archive_date, folders=folders)
    candidates += _scan_old_daily_reports(
        vault,
        threshold_days=old_daily_reports_days,
        archive_date=archive_date,
        now=now,
        folders=folders,
    )
    candidates += _scan_empty_folders(vault, folders=folders)

    return CleanupPlan(
        vault_path=str(vault),
        scanned_at=now.isoformat(timespec="seconds"),
        candidates=candidates,
    )


def apply_cleanup(
    plan: CleanupPlan,
    *,
    selected: list[CleanupCandidate] | None = None,
    dry_run: bool = True,
    vault: Path | None = None,
    folders: VaultFoldersConfig | None = None,
) -> list[CleanupResult]:
    """선택된 후보를 archive 폴더로 이동.

    Args:
        plan: scan 결과 (vault 경로 포함).
        selected: 이동할 후보 (None이면 plan.candidates 전체).
        dry_run: True이면 실제 이동 없이 결과만 기록.
        vault: plan.vault_path 대신 명시 (테스트용).
    """
    if folders is None:
        from synapse_memory.config import get_config

        folders = get_config().vault_folders

    items = selected if selected is not None else plan.candidates
    vault_path = vault or Path(plan.vault_path)
    results: list[CleanupResult] = []

    for c in items:
        try:
            source = Path(c.source_path)
            try:
                rel = source.relative_to(vault_path)
            except ValueError:
                rel = None
            if rel is not None and _is_protected(rel, folders):
                results.append(
                    CleanupResult(
                        candidate=c,
                        status="skipped",
                        detail="보호 경로 — 이동 안 함",
                    )
                )
                continue
            if not source.exists():
                results.append(
                    CleanupResult(
                        candidate=c,
                        status="skipped",
                        detail="원본 없음 (이미 이동되었거나 삭제됨)",
                    )
                )
                continue

            if dry_run:
                results.append(CleanupResult(candidate=c, status="dry_run", detail="이동 예정"))
                continue

            if c.kind == CleanupKind.EMPTY_FOLDER:
                if source.is_dir() and not any(source.iterdir()):
                    source.rmdir()
                    results.append(CleanupResult(candidate=c, status="moved", detail="폴더 제거"))
                else:
                    results.append(
                        CleanupResult(
                            candidate=c,
                            status="skipped",
                            detail="더 이상 비어 있지 않음",
                        )
                    )
                continue

            target = Path(c.target_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            results.append(CleanupResult(candidate=c, status="moved", detail=str(target)))
        except Exception as e:
            results.append(CleanupResult(candidate=c, status="failed", detail=str(e)))

    return results


def write_cleanup_manifest(
    vault: Path,
    results: list[CleanupResult],
    *,
    archive_date: str | None = None,
    folders: VaultFoldersConfig | None = None,
) -> Path:
    """이동 결과를 매니페스트 마크다운으로 vault에 기록.

    위치: 설정된 CleanupReports 폴더의 ``YYYY-MM-DD.md``
    """
    if folders is None:
        from synapse_memory.config import get_config

        folders = get_config().vault_folders

    archive_date = archive_date or datetime.datetime.now().strftime("%Y-%m-%d")
    report_dir = _vault_path(
        vault,
        folders.system.ai.cleanup_reports,
        key="vault_folders.system.ai.cleanup_reports",
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / f"{archive_date}.md"

    moved = [r for r in results if r.status == "moved"]
    dry = [r for r in results if r.status == "dry_run"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    fm = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "archive_date": archive_date,
        "summary": {
            "moved": len(moved),
            "dry_run": len(dry),
            "skipped": len(skipped),
            "failed": len(failed),
        },
        "pinned": True,
    }
    lines: list[str] = ["---"]
    lines.append(yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip())
    lines.append("---")
    lines.append("")
    lines.append(f"# Cleanup Report — {archive_date}")
    lines.append("")
    lines.append(
        f"이동 {len(moved)} · 건너뜀 {len(skipped)} · 실패 {len(failed)} · dry-run {len(dry)}"
    )
    lines.append("")

    def _section(title: str, group: list[CleanupResult]) -> None:
        if not group:
            return
        lines.append(f"## {title}")
        lines.append("")
        for r in group:
            c = r.candidate
            lines.append(f"- **{c.kind.value}** — {c.reason}")
            lines.append(f"  - 원본: `{c.source_path}`")
            lines.append(f"  - 목적지: `{c.target_path}`")
            if r.detail:
                lines.append(f"  - 상세: {r.detail}")
        lines.append("")

    _section("이동된 항목", moved)
    _section("Dry-run 예정", dry)
    _section("건너뜀", skipped)
    _section("실패", failed)

    if moved:
        lines.append("## 롤백 가이드")
        lines.append("")
        lines.append(
            "각 항목의 *원본 경로*로 *목적지 경로*의 파일을 되옮기면 원상복구됩니다. "
            "셸 한 줄로 한 항목씩 복구:"
        )
        lines.append("")
        lines.append("```bash")
        lines.append("# 예: 한 항목 복구")
        lines.append("mv '<목적지>' '<원본>'")
        lines.append("```")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
