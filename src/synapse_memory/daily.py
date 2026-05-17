"""일일 자동 파이프라인 — 5분 안에 끝나는 통합 워크플로.

Steps (incremental — 이미 처리된 건 자동 skip)::

    1. collect claude-code           (mirror 새 줄만)
    2. collect obsidian              (변경 .md만)
    3. cluster classify --resume     (새 cluster만)
    4. card generate (--force=False) (새 cluster만 Card 생성)
    5. rag index                     (Card upsert)
    6. persona update-profile        (오늘 활동 분석 → MemoryInbox PR)
    7. report                        (DailyReport 작성)

--only로 일부 단계만 건너뛰기. --dry-run으로 단계만 출력.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import datetime
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synapse_memory.status import StatusSink, StatusWriter

StageAction = Callable[[], Any]


class StageStatus:
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class DailyStage:
    name: str
    description: str
    requires: tuple[str, ...] = ()


DAILY_STAGES = (
    DailyStage("collect_claude_code", "Claude Code 로그 mirror"),
    DailyStage("collect_obsidian", "Obsidian vault mirror"),
    DailyStage("classify", "신규 cluster 분류"),
    DailyStage("generate", "Project/Company Card 생성", ("classify",)),
    DailyStage("index", "Card RAG index", ("generate",)),
    DailyStage(
        "update_profile",
        "ProfileFact/DecisionPattern 후보 추출",
        ("collect_claude_code", "classify", "generate"),
    ),
    DailyStage("report", "DailyReport 작성"),
)

# 단계 이름 — CLI --only / --skip / --resume-from 에서 사용
STEPS = tuple(stage.name for stage in DAILY_STAGES)


@dataclass
class StepResult:
    name: str
    elapsed: float
    status: str = StageStatus.SUCCESS
    summary: str = ""
    error: str = ""
    skip_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == StageStatus.SUCCESS

    @classmethod
    def success(cls, name: str, elapsed: float, summary: str = "") -> StepResult:
        return cls(
            name=name,
            elapsed=elapsed,
            status=StageStatus.SUCCESS,
            summary=summary,
        )

    @classmethod
    def failed(cls, name: str, elapsed: float, error: str) -> StepResult:
        return cls(
            name=name,
            elapsed=elapsed,
            status=StageStatus.FAILED,
            error=error,
        )

    @classmethod
    def skipped(cls, name: str, reason: str) -> StepResult:
        return cls(
            name=name,
            elapsed=0.0,
            status=StageStatus.SKIPPED,
            skip_reason=reason,
        )


@dataclass
class DailyResult:
    steps: list[StepResult] = field(default_factory=list)
    total_elapsed: float = 0.0
    resume_from: str | None = None
    report_path: Path | None = None
    report_error: str = ""

    @property
    def errors(self) -> int:
        return sum(1 for s in self.steps if s.status == StageStatus.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for s in self.steps if s.status == StageStatus.SKIPPED)


def validate_daily_stages(stages: tuple[DailyStage, ...] = DAILY_STAGES) -> None:
    seen: set[str] = set()
    for stage in stages:
        if stage.name in seen:
            raise ValueError(f"duplicate daily stage: {stage.name}")
        seen.add(stage.name)
    for stage in stages:
        for dependency in stage.requires:
            if dependency not in seen:
                raise ValueError(
                    f"unknown dependency for {stage.name}: {dependency}"
                )


def _run_step(
    name: str,
    func: Callable[[], Any],
    *,
    on_log: Callable[[str], None] = print,
) -> StepResult:
    on_log(f"\n=== [{name}] ===")
    t0 = time.monotonic()
    try:
        summary = func() or ""
    except Exception as exc:
        elapsed = time.monotonic() - t0
        on_log(f"  실패: {exc}")
        return StepResult.failed(name, elapsed, str(exc))
    elapsed = time.monotonic() - t0
    on_log(f"  ({elapsed:.1f}s) {summary}")
    return StepResult.success(name, elapsed, str(summary))


def _emit_progress(
    on_log: Callable[[str], None],
    *,
    index: int,
    total: int,
    label: str,
    status: str,
    elapsed: float | None = None,
    status_sink: StatusSink | None = None,
) -> None:
    """클러스터 루프 진행 한 줄 출력 — `[i/N] label ... status`.

    백그라운드/파이프 환경에서도 즉시 보이도록 stdout flush를 보장한다.
    `status_sink`가 주어지면 status JSON에 현재 item도 반영한다.
    """
    suffix = f" ({elapsed:.1f}s)" if elapsed is not None else ""
    on_log(f"  [{index}/{total}] {label} ... {status}{suffix}")
    if status_sink is not None:
        status_sink.update_item(index=index, total=total, label=label)
    import sys

    with contextlib.suppress(Exception):
        sys.stdout.flush()


def _resume_skip_reason(resume_from: str) -> str:
    return f"resume before {resume_from}"


def _is_resume_skip(step: StepResult) -> bool:
    return step.status == StageStatus.SKIPPED and step.skip_reason.startswith(
        "resume before "
    )


def _blocking_dependency(
    stage: DailyStage,
    results_by_name: Mapping[str, StepResult],
) -> str | None:
    for dependency in stage.requires:
        upstream = results_by_name.get(dependency)
        if upstream is None:
            continue
        if upstream.status == StageStatus.FAILED:
            return dependency
        if upstream.status == StageStatus.SKIPPED and not _is_resume_skip(upstream):
            return dependency
    return None


def _build_stage_actions(
    *,
    classify_model: str,
    generate_model: str,
    profile_model: str,
    profile_sample_lines: int,
    profile_facts_only: bool,
    on_log: Callable[[str], None],
    status_sink: StatusSink | None = None,
    quick_since_days: int | None = None,
    quick_max_new_clusters: int | None = None,
) -> dict[str, StageAction]:
    """stage 별 action 사전. ``quick_*`` 인자는 ``--quick`` 모드 cutoff 를 활성화."""
    obsidian_action: StageAction = (
        _build_collect_obsidian_action(since_days=quick_since_days)
        if quick_since_days is not None
        else _collect_obsidian_action
    )
    return {
        "collect_claude_code": _collect_claude_code_action,
        "collect_obsidian": obsidian_action,
        "classify": _build_classify_action(
            classify_model,
            on_log,
            status_sink,
            max_new_clusters=quick_max_new_clusters,
        ),
        "generate": _build_generate_action(generate_model, on_log, status_sink),
        "index": _index_action,
        "update_profile": _build_update_profile_action(
            profile_model=profile_model,
            profile_sample_lines=profile_sample_lines,
            profile_facts_only=profile_facts_only,
        ),
        "report": lambda: "",
    }


def _collect_claude_code_action() -> str:
    from synapse_memory.collectors.claude_code import collect_claude_code

    stats = collect_claude_code()
    return stats.summary()


def _build_collect_obsidian_action(since_days: int | None = None) -> StageAction:
    def step() -> str:
        from synapse_memory.collectors.obsidian import collect_obsidian

        stats = collect_obsidian(since_days=since_days)
        return stats.summary()

    return step


# 기존 함수 — 시그니처 보존 (테스트 호환). 새 경로는 _build_collect_obsidian_action.
def _collect_obsidian_action() -> str:
    from synapse_memory.collectors.obsidian import collect_obsidian

    stats = collect_obsidian()
    return stats.summary()


def _build_classify_action(
    classify_model: str,
    on_log: Callable[[str], None],
    status_sink: StatusSink | None = None,
    max_new_clusters: int | None = None,
) -> StageAction:
    def step() -> str:
        from synapse_memory.cards.auto_classify import (
            classify_cluster,
            load_classifications,
            save_classifications,
        )
        from synapse_memory.clusters import identify_clusters
        from synapse_memory.collectors.obsidian import get_vault_path as obs_path
        from synapse_memory.llm import detect_ai_environment

        env = detect_ai_environment(model=classify_model)
        if not env.ready:
            raise RuntimeError("AI provider 미설치")
        clusters = identify_clusters()
        existing = load_classifications()
        new_clusters = [c for c in clusters if c.cluster_id not in existing]
        if not new_clusters:
            return "신규 cluster 없음"
        # --quick 모드: AI 호출 수 제한 (cluster 당 1회 호출이라 daily 시간 직접 지배)
        truncated = 0
        if max_new_clusters is not None and len(new_clusters) > max_new_clusters:
            truncated = len(new_clusters) - max_new_clusters
            new_clusters = new_clusters[:max_new_clusters]
        obs_root = obs_path()
        cls_dict = dict(existing)
        failed = 0
        total = len(new_clusters)
        for i, c in enumerate(new_clusters, start=1):
            t_cluster = time.monotonic()
            try:
                cls = classify_cluster(
                    c, obs_root=obs_root, ai_env=env, model=classify_model
                )
                cls_dict[c.cluster_id] = cls
                _emit_progress(
                    on_log,
                    index=i,
                    total=total,
                    label=c.cluster_id,
                    status="ok",
                    elapsed=time.monotonic() - t_cluster,
                    status_sink=status_sink,
                )
            except Exception as exc:
                failed += 1
                _emit_progress(
                    on_log,
                    index=i,
                    total=total,
                    label=c.cluster_id,
                    status=f"실패: {exc}",
                    elapsed=time.monotonic() - t_cluster,
                    status_sink=status_sink,
                )
        save_classifications(cls_dict)
        suffix = f", 실패 {failed}개" if failed else ""
        truncate_note = (
            f" (quick: {truncated}개 다음 호출로 deferred)" if truncated else ""
        )
        return f"신규 {len(new_clusters)}개 분류{suffix}{truncate_note}"

    return step


def _build_generate_action(
    generate_model: str,
    on_log: Callable[[str], None],
    status_sink: StatusSink | None = None,
) -> StageAction:
    def step() -> str:
        from synapse_memory.cards.auto_classify import load_classifications
        from synapse_memory.cards.auto_generate import (
            generate_company_card,
            generate_project_card,
        )
        from synapse_memory.cards.company import companies_dir, save_company_card
        from synapse_memory.cards.project import projects_dir, save_project_card
        from synapse_memory.clusters import identify_clusters
        from synapse_memory.collectors.obsidian import get_vault_path as obs_path
        from synapse_memory.llm import detect_ai_environment

        env = detect_ai_environment(model=generate_model)
        if not env.ready:
            raise RuntimeError("AI provider 미설치")
        classifications = load_classifications()
        if not classifications:
            return "classifications 비어있음"
        clusters = {c.cluster_id: c for c in identify_clusters()}
        obs_root = obs_path()

        pending: list[tuple[str, Any, str, Path]] = []
        for cid, cls in classifications.items():
            if cls.kind not in ("project", "company"):
                continue
            if cid not in clusters:
                continue
            if cls.kind == "project":
                target = projects_dir() / f"{cid}.md"
            else:
                target = companies_dir() / f"{cid}.md"
            if target.exists():
                continue
            pending.append((cid, cls, cls.kind, target))

        if not pending:
            return "신규 Card 없음"

        created = 0
        failed = 0
        total = len(pending)
        for i, (cid, cls, kind, _target) in enumerate(pending, start=1):
            label = f"{cid} ({kind})"
            t_card = time.monotonic()
            try:
                if kind == "project":
                    card = generate_project_card(
                        clusters[cid],
                        candidate_name=cls.candidate_name,
                        obs_root=obs_root,
                        ai_env=env,
                        model=generate_model,
                    )
                    save_project_card(card)
                else:
                    card_c = generate_company_card(
                        clusters[cid],
                        candidate_name=cls.candidate_name,
                        obs_root=obs_root,
                        ai_env=env,
                        model=generate_model,
                    )
                    save_company_card(card_c)
                created += 1
                _emit_progress(
                    on_log,
                    index=i,
                    total=total,
                    label=label,
                    status="ok",
                    elapsed=time.monotonic() - t_card,
                    status_sink=status_sink,
                )
            except Exception as exc:
                failed += 1
                _emit_progress(
                    on_log,
                    index=i,
                    total=total,
                    label=label,
                    status=f"실패: {exc}",
                    elapsed=time.monotonic() - t_card,
                    status_sink=status_sink,
                )
        suffix = f", 실패 {failed}개" if failed else ""
        summary = f"신규 Card {created}개 생성{suffix}"
        # 생성 0, 실패>0 인 완전 실패는 단계 자체를 FAILED 로 표시해 update_profile
        # 등 후속 단계가 자동으로 skip 되도록 한다.
        if created == 0 and failed > 0:
            raise RuntimeError(summary)
        return summary

    return step


def _index_action() -> str:
    from synapse_memory.rag import index_cards

    stats = index_cards()
    return f"project={stats.project_cards} company={stats.company_cards}"


def _build_update_profile_action(
    *,
    profile_model: str,
    profile_sample_lines: int,
    profile_facts_only: bool,
) -> StageAction:
    def step() -> str:
        from synapse_memory.llm import detect_ai_environment
        from synapse_memory.profile.extract import (
            extract_decision_patterns,
            extract_profile_facts,
            save_profile_update,
        )

        env = detect_ai_environment(model=profile_model)
        if not env.ready:
            raise RuntimeError("AI provider 미설치")
        facts = extract_profile_facts(
            sample_lines=profile_sample_lines,
            model=profile_model,
            ai_env=env,
        )
        patterns = []
        if not profile_facts_only:
            patterns = extract_decision_patterns(
                sample_lines=profile_sample_lines,
                model=profile_model,
                ai_env=env,
            )
        path = save_profile_update(facts, patterns)
        return f"fact={len(facts)} pattern={len(patterns)} → {path.name}"

    return step


def _build_report_action(result: DailyResult) -> StageAction:
    def step() -> str:
        path = write_daily_report(result)
        result.report_path = path
        return f"DailyReports/{path.name}"

    return step


def write_daily_report(
    result: DailyResult,
    *,
    date: datetime.date | None = None,
    vault_path: Path | None = None,
) -> Path:
    from synapse_memory.collectors.obsidian import get_vault_path
    from synapse_memory.config import get_config
    from synapse_memory.folders import year_month_path

    report_date = date or datetime.date.today()
    root = vault_path or get_vault_path()
    report_base = root / get_config().vault_folders.system.ai.daily_reports
    report_dir = year_month_path(report_base, report_date)
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{report_date.isoformat()}.md"
    path.write_text(
        render_daily_report(
            result,
            date=report_date.isoformat(),
            est_usd=_estimate_usd_today(report_date),
        ),
        encoding="utf-8",
    )
    return path


def render_daily_report(
    result: DailyResult,
    *,
    date: str,
    est_usd: float,
) -> str:
    lines = [
        "---",
        f"date: {date}",
        f"total_elapsed_s: {result.total_elapsed:.1f}",
        f"errors_count: {result.errors}",
        f"skipped_count: {result.skipped}",
        f"new_cards: {_extract_first_int(result.steps, '신규 Card')}",
        f"new_facts: {_extract_first_int(result.steps, 'fact=')}",
        f"est_usd: {est_usd:.4f}",
        f"resume_from: {result.resume_from or ''}",
        "---",
        "",
        f"# Daily Report — {date}",
        "",
        "## Stage Summary",
        "",
        "| Stage | Status | Elapsed | Summary | Reason |",
        "|---|---:|---:|---|---|",
    ]
    for step in result.steps:
        reason = step.error or step.skip_reason
        lines.append(
            "| "
            f"{step.name} | {step.status} | {step.elapsed:.1f}s | "
            f"{_clean_cell(step.summary)} | {_clean_cell(reason)} |"
        )

    failures = [step for step in result.steps if step.status == StageStatus.FAILED]
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(f"- {step.name}: {step.error}" for step in failures)
    else:
        lines.append("- 없음")

    lines.extend(["", "## Resume", ""])
    if failures:
        first_failure = failures[0].name
        lines.extend(
            [
                "Re-run from the first failed stage:",
                "",
                "```bash",
                f"synapse-memory daily --resume-from {first_failure}",
                "```",
            ]
        )
    elif result.resume_from:
        lines.append(f"Resumed from `{result.resume_from}`.")
    else:
        lines.append("Resume not needed.")
    return "\n".join(lines) + "\n"


def _clean_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def _extract_first_int(steps: list[StepResult], marker: str) -> int:
    import re

    for step in steps:
        if marker not in step.summary:
            continue
        tail = step.summary.split(marker, 1)[1]
        match = re.search(r"\d+", tail)
        if match:
            return int(match.group(0))
    return 0


def _estimate_usd_today(date: datetime.date) -> float:
    try:
        from synapse_memory.cost.summary import load_summary

        end = datetime.datetime.combine(
            date + datetime.timedelta(days=1),
            datetime.time.min,
            tzinfo=datetime.UTC,
        )
        return load_summary(days=1, by="command", now=end).total.usd
    except Exception:
        return 0.0


_QUICK_DEFAULT_DAYS = 7
_QUICK_DEFAULT_MAX_CLUSTERS = 10


def run_daily(
    *,
    only: set[str] | None = None,
    skip: set[str] | None = None,
    resume_from: str | None = None,
    classify_model: str = "haiku",
    generate_model: str = "sonnet",
    profile_model: str = "sonnet",
    profile_sample_lines: int = 200,
    profile_facts_only: bool = False,
    quick: bool = False,
    quick_days: int = _QUICK_DEFAULT_DAYS,
    quick_max_clusters: int = _QUICK_DEFAULT_MAX_CLUSTERS,
    dry_run: bool = False,
    stage_actions: Mapping[str, StageAction] | None = None,
    on_log: Callable[[str], None] = print,
    status_sink: StatusSink | None = None,
) -> DailyResult:
    """일일 파이프라인 실행.

    Args:
        only: 이 단계 이름들만 실행. None이면 전체.
        skip: 제외할 단계.
        classify_model / generate_model / profile_model: 단계별 AI 모델.
        profile_sample_lines: update-profile의 history 분석 줄 수.
        profile_facts_only: DecisionPattern 추출 skip.
        quick: B1 quick mode (eng-review 2026-05-13). True 시:
            - collect_obsidian: ``since_days=quick_days`` cutoff
            - classify: ``max_new_clusters=quick_max_clusters`` cap
            - update_profile: auto-skip (heavy AI 호출 회피)
            full pipeline 은 별도 cron 또는 수동 ``daily`` (no flag) 호출.
            ChromaDB write 동시성 회피를 위해 quick + full 동시 실행 금지.
        quick_days: ``quick=True`` 일 때 mtime cutoff 일수. 기본 7.
        quick_max_clusters: ``quick=True`` 일 때 classify 최대 cluster 수. 기본 10.
        dry_run: True면 단계 이름만 출력.
        stage_actions: stage body override (테스트용).
        on_log: print 대체 (테스트용).
    """
    validate_daily_stages()
    if resume_from is not None and resume_from not in STEPS:
        raise ValueError(
            f"unknown daily stage: {resume_from}\n"
            f"valid stages: {', '.join(STEPS)}"
        )
    if quick and quick_days < 0:
        raise ValueError(f"quick_days must be >= 0, got {quick_days}")
    if quick and quick_max_clusters < 0:
        raise ValueError(
            f"quick_max_clusters must be >= 0, got {quick_max_clusters}"
        )

    result = DailyResult(resume_from=resume_from)
    t_start = time.monotonic()

    selected = set(only) if only else set(STEPS)
    if skip:
        selected -= set(skip)
    # quick 모드: update_profile auto-skip (heavy AI 호출).
    # 명시적 only= 로 update_profile 요청 시에는 사용자 의도 우선.
    if quick and only is None:
        selected.discard("update_profile")
    if resume_from is not None:
        resume_index = STEPS.index(resume_from)
        selected -= set(STEPS[:resume_index])

    if dry_run:
        on_log("[DRY RUN] 실행 단계:")
        for i, s in enumerate(STEPS):
            resume_skipped = resume_from is not None and i < STEPS.index(resume_from)
            mark = "  [x]" if s in selected else "  [ ]"
            suffix = " (resume skip)" if resume_skipped else ""
            on_log(f"{mark} {s}{suffix}")
        return result

    if status_sink is None:
        try:
            status_sink = StatusWriter(total_stages=len(STEPS))
        except Exception:
            status_sink = StatusSink()

    actions = _build_stage_actions(
        classify_model=classify_model,
        generate_model=generate_model,
        profile_model=profile_model,
        profile_sample_lines=profile_sample_lines,
        profile_facts_only=profile_facts_only,
        on_log=on_log,
        status_sink=status_sink,
        quick_since_days=quick_days if quick else None,
        quick_max_new_clusters=quick_max_clusters if quick else None,
    )
    if stage_actions:
        actions.update(stage_actions)

    results_by_name: dict[str, StepResult] = {}
    for i, stage in enumerate(DAILY_STAGES):
        if resume_from is not None and i < STEPS.index(resume_from):
            step_result = StepResult.skipped(stage.name, _resume_skip_reason(resume_from))
            result.steps.append(step_result)
            results_by_name[stage.name] = step_result
            continue
        if stage.name not in selected:
            continue
        dependency = _blocking_dependency(stage, results_by_name)
        if dependency is not None:
            step_result = StepResult.skipped(stage.name, f"requires {dependency}")
            on_log(f"\n=== [{stage.name}] ===")
            on_log(f"  건너뜀: {step_result.skip_reason}")
        else:
            status_sink.begin_stage(stage.name, i + 1)
            action = actions[stage.name]
            if stage.name == "report" and stage.name not in (stage_actions or {}):
                action = _build_report_action(result)
            step_result = _run_step(stage.name, action, on_log=on_log)
            status_sink.end_stage(
                stage.name,
                failed=step_result.status == StageStatus.FAILED,
            )
        result.steps.append(step_result)
        results_by_name[stage.name] = step_result

    result.total_elapsed = time.monotonic() - t_start
    status_sink.finish(errors=result.errors)
    return result
