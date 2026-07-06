"""일일 자동 파이프라인 — 5분 안에 끝나는 통합 워크플로.

Steps (incremental — 이미 처리된 건 자동 skip)::

    1.  collect claude-code           (mirror 새 줄만)
    2.  collect codex                 (~/.codex 새 줄만)
    3.  collect cursor                (Cursor IDE SQLite snapshot)
    4.  collect continue.dev          (~/.continue 세션 JSON)
    5.  collect aider                 (~/.aider.* append-only)
    6.  collect day-one               (Day One journal)
    7.  collect gmail-sent            (opt-in)
    8.  collect obsidian              (변경 .md만)
    9.  cluster classify --resume     (새 cluster만)
    10. card generate (--force=False) (새 cluster만 Card 생성)
    11. wiki/card provider sync       (provider-only context refresh)
    12. persona update-profile        (오늘 활동 분석 → MemoryInbox PR)
    13. report                        (DailyReport 작성)
    14. lint                          (wiki 구조 lint)

--only로 일부 단계만 건너뛰기. --dry-run으로 단계만 출력.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import datetime
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synapse_memory.status import DailyRunLock, StatusSink, StatusWriter

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
    DailyStage("collect_codex", "Codex CLI 로그 mirror"),
    DailyStage("collect_cursor", "Cursor IDE 로그 mirror"),
    DailyStage("collect_continue", "Continue.dev 세션 mirror"),
    DailyStage("collect_aider", "Aider 대화 mirror"),
    DailyStage("collect_day_one", "Day One journal mirror"),
    DailyStage("collect_gmail_sent", "Gmail Sent mirror (opt-in)"),
    DailyStage("collect_obsidian", "Obsidian vault mirror"),
    DailyStage("classify", "신규 cluster 분류"),
    DailyStage("generate", "Project/Company Card 생성", ("classify",)),
    DailyStage(
        "update_profile",
        "ProfileFact/DecisionPattern 후보 추출",
        ("collect_claude_code", "classify", "generate"),
    ),
    DailyStage("report", "DailyReport 작성"),
    DailyStage("lint", "Wiki 구조 lint"),
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
    # update_profile stage 의 구조화 결과 — DailyReport 의 "Profile Pipeline"
    # 섹션 렌더에 사용. 값 키: raw_facts, raw_patterns, promoted_facts,
    # promoted_patterns, awaiting_facts, awaiting_patterns, vault_dropped,
    # dismissed_total, dismissed_expired, dismissed_reason_counts.
    profile_meta: dict[str, object] = field(default_factory=dict)

    @property
    def errors(self) -> int:
        return sum(1 for s in self.steps if s.status == StageStatus.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for s in self.steps if s.status == StageStatus.SKIPPED)

    @property
    def warnings(self) -> int:
        return sum(_summary_error_count(s.summary) for s in self.steps if s.ok)


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


def _validate_stage_names(kind: str, names: set[str] | None) -> None:
    if not names:
        return
    unknown = sorted(names - set(STEPS))
    if unknown:
        raise ValueError(
            f"unknown daily stage in {kind}: {', '.join(unknown)}\n"
            f"valid stages: {', '.join(STEPS)}"
        )


def _summary_error_count(summary: str) -> int:
    match = re.search(r"\berrors=(\d+)\b", summary)
    return int(match.group(1)) if match else 0


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
            return dependency
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
    result: DailyResult | None = None,
) -> dict[str, StageAction]:
    """stage 별 action 사전. ``quick_*`` 인자는 ``--quick`` 모드 cutoff 를 활성화.

    ``result`` 가 주어지면 update_profile stage 의 구조화 통계가
    ``result.profile_meta`` 에 채워져 DailyReport 의 Profile Pipeline 섹션 렌더에
    사용된다.
    """
    obsidian_action: StageAction = (
        _build_collect_obsidian_action(since_days=quick_since_days)
        if quick_since_days is not None
        else _collect_obsidian_action
    )
    return {
        "collect_claude_code": _collect_claude_code_action,
        "collect_codex": _collect_codex_action,
        "collect_cursor": _collect_cursor_action,
        "collect_continue": _collect_continue_action,
        "collect_aider": _collect_aider_action,
        "collect_day_one": _collect_day_one_action,
        "collect_gmail_sent": _collect_gmail_sent_action,
        "collect_obsidian": obsidian_action,
        "classify": _build_classify_action(
            classify_model,
            on_log,
            status_sink,
            max_new_clusters=quick_max_new_clusters,
        ),
        "generate": _build_generate_action(generate_model, on_log, status_sink),
        "update_profile": _build_update_profile_action(
            profile_model=profile_model,
            profile_sample_lines=profile_sample_lines,
            profile_facts_only=profile_facts_only,
            result=result,
        ),
        "report": lambda: "",
        "lint": _lint_action,
    }


def _collect_claude_code_action() -> str:
    from synapse_memory.collectors.claude_code import collect_claude_code

    stats = collect_claude_code()
    return stats.summary()


def _collect_codex_action() -> str:
    from synapse_memory.collectors.codex import collect_codex

    stats = collect_codex()
    return stats.summary()


def _collect_cursor_action() -> str:
    from synapse_memory.collectors.cursor import collect_cursor

    stats = collect_cursor()
    return stats.summary()


def _collect_continue_action() -> str:
    from synapse_memory.collectors.continue_dev import collect_continue

    stats = collect_continue()
    return stats.summary()


def _collect_aider_action() -> str:
    from synapse_memory.collectors.aider import collect_aider

    stats = collect_aider()
    return stats.summary()


def _collect_day_one_action() -> str:
    from synapse_memory.collectors.day_one import collect_day_one

    stats = collect_day_one()
    return stats.summary()


def _collect_gmail_sent_action() -> str:
    from synapse_memory.collectors.gmail_sent import collect_gmail_sent

    stats = collect_gmail_sent()
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


def _build_update_profile_action(
    *,
    profile_model: str,
    profile_sample_lines: int,
    profile_facts_only: bool,
    result: DailyResult | None = None,
) -> StageAction:
    def step() -> str:
        from synapse_memory.collectors.obsidian.mirror import get_vault_path
        from synapse_memory.config import get_config
        from synapse_memory.llm import detect_ai_environment
        from synapse_memory.profile.dedupe import (
            dedupe_against_vault,
            parse_decision_pattern_triggers,
            parse_profile_facts,
        )
        from synapse_memory.profile.dismissed import (
            dismissed_path,
            load_dismissed,
        )
        from synapse_memory.profile.extract import (
            extract_decision_patterns,
            extract_profile_facts,
            save_profile_update,
        )
        from synapse_memory.profile.ledger import (
            enrich_promoted_patterns,
            load_ledger,
            mark_promoted,
            promote_candidates,
            record_extraction,
            save_ledger,
        )

        env = detect_ai_environment(model=profile_model)
        if not env.ready:
            raise RuntimeError("AI provider 미설치")

        cfg = get_config()
        vault = get_vault_path()
        ai_folders = cfg.vault_folders.system.ai
        profile_path = vault / ai_folders.profile
        dp_path = vault / ai_folders.decision_patterns
        existing_facts = parse_profile_facts(profile_path)
        existing_triggers = parse_decision_pattern_triggers(dp_path)
        dismissed = load_dismissed(dismissed_path(vault))
        # strong (misclassified+irrelevant) 는 별도 섹션으로 LLM 에 강한 차단 신호.
        strong_facts = sorted(dismissed.strong_facts())
        strong_patterns = sorted(dismissed.strong_patterns())
        # normal 제외 = vault + dismissed 전체. strong 항목이 두 섹션에 중복돼도
        # LLM 측 무해 (차단 효과만 강화) — 단순성 우선.
        excluded_facts = existing_facts + sorted(dismissed.facts)
        excluded_triggers = existing_triggers + sorted(dismissed.patterns)

        # 1) 추출 — claude-code + codex history, negative example 주입.
        raw_facts = extract_profile_facts(
            sample_lines=profile_sample_lines,
            model=profile_model,
            ai_env=env,
            excluded_statements=excluded_facts,
            excluded_statements_strong=strong_facts,
        )
        from synapse_memory.profile.schema import DecisionPattern as _DP
        raw_patterns: list[_DP] = []
        if not profile_facts_only:
            raw_patterns = extract_decision_patterns(
                sample_lines=profile_sample_lines,
                model=profile_model,
                ai_env=env,
                excluded_triggers=excluded_triggers,
                excluded_triggers_strong=strong_patterns,
            )

        # 2) ledger 누적 + promotion — multi-day cross-validation.
        ledger = load_ledger()
        record_extraction(ledger, raw_facts, raw_patterns)
        promoted_facts, promoted_patterns, promo_report = promote_candidates(
            ledger,
            facts_input=raw_facts,
            patterns_input=raw_patterns,
            min_count=cfg.profile.promotion_min_count,
            window_days=cfg.profile.promotion_window_days,
            fast_path_confidence=cfg.profile.fast_path_confidence,
        )
        # pattern 의 action/rationale 은 ledger 가 안 저장 — 오늘 호출 결과로 보강.
        promoted_patterns = enrich_promoted_patterns(promoted_patterns, raw_patterns)

        # 3) 후처리 dedupe — vault/dismissed 와 비교 안전망.
        facts, patterns, report = dedupe_against_vault(
            promoted_facts,
            promoted_patterns,
            profile_path=profile_path,
            decision_patterns_path=dp_path,
            dismissed_facts=dismissed.facts,
            dismissed_patterns=dismissed.patterns,
        )

        # 4) ledger 마크 + persist — promoted 만 마크 (dedupe 로 drop 된 건 다음 호출에서 다시).
        mark_promoted(ledger, facts, patterns)
        save_ledger(ledger)

        # 관찰성: DailyReport 의 Profile Pipeline 섹션 렌더용 구조화 메타.
        if result is not None:
            from collections import Counter as _Counter

            reason_counts: dict[str, int] = {}
            try:
                dpath = dismissed_path(vault)
                if dpath.is_file():
                    import json as _json

                    reasons: list[str] = []
                    for raw_line in dpath.read_text(encoding="utf-8").splitlines():
                        line = raw_line.strip()
                        if not line or line.startswith("#"):
                            continue
                        try:
                            obj = _json.loads(line)
                        except _json.JSONDecodeError:
                            continue
                        if not isinstance(obj, dict):
                            continue
                        r = obj.get("reason", "")
                        if isinstance(r, str):
                            reasons.append(r)
                    reason_counts = dict(_Counter(reasons))
            except OSError:
                reason_counts = {}

            result.profile_meta = {
                "raw_facts": len(raw_facts),
                "raw_patterns": len(raw_patterns),
                "promoted_facts": promo_report.promoted_fact_count,
                "promoted_patterns": promo_report.promoted_pattern_count,
                "awaiting_facts": promo_report.awaiting_fact_count,
                "awaiting_patterns": promo_report.awaiting_pattern_count,
                "vault_dropped": report.total_dropped,
                "dismissed_total": dismissed.total,
                "dismissed_expired": dismissed.expired_count,
                "dismissed_reason_counts": reason_counts,
                "candidate_facts": len(facts),
                "candidate_patterns": len(patterns),
            }

        dismiss_note = (
            f" dismissed_idx={dismissed.total}"
            + (
                f" (만료 {dismissed.expired_count} 재노출)"
                if dismissed.expired_count
                else ""
            )
            if dismissed.total or dismissed.expired_count
            else ""
        )
        ledger_note = (
            f" [ledger {promo_report.summary()}]"
        )

        if not facts and not patterns:
            return (
                f"신규 fact/pattern 없음 — raw {len(raw_facts)}/{len(raw_patterns)} "
                f"→ promotion 대기"
                f"{ledger_note}{dismiss_note}"
            )

        path = save_profile_update(facts, patterns, ledger=ledger)
        return (
            f"fact={len(facts)} pattern={len(patterns)} "
            f"(vault dedupe -{report.total_dropped}{dismiss_note}{ledger_note}) "
            f"→ {path.name}"
        )

    return step


def _build_report_action(result: DailyResult) -> StageAction:
    def step() -> str:
        path = write_daily_report(result)
        result.report_path = path
        return f"DailyReports/{path.name}"

    return step


def _run_report_step(
    result: DailyResult,
    *,
    t_start: float,
    on_log: Callable[[str], None] = print,
) -> StepResult:
    name = "report"
    on_log(f"\n=== [{name}] ===")
    t0 = time.monotonic()
    appended = False
    step_result: StepResult | None = None
    try:
        result.total_elapsed = time.monotonic() - t_start
        path = write_daily_report(result)
        result.report_path = path
        elapsed = time.monotonic() - t0
        step_result = StepResult.success(
            name,
            elapsed,
            f"DailyReports/{path.name}",
        )
        result.steps.append(step_result)
        appended = True
        result.total_elapsed = time.monotonic() - t_start
        write_daily_report(result)
        on_log(f"  ({elapsed:.1f}s) {step_result.summary}")
        return step_result
    except Exception as exc:
        elapsed = time.monotonic() - t0
        on_log(f"  실패: {exc}")
        return StepResult.failed(name, elapsed, str(exc))
    finally:
        if appended and result.steps and result.steps[-1] is step_result:
            result.steps.pop()


def _lint_action() -> str:
    from synapse_memory.wiki.lint import run_lint

    report = run_lint()
    return (
        f"backlinks+={report.backlinks_added} "
        f"dead_links-={report.dead_links_removed}"
    )


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
        f"warnings_count: {result.warnings}",
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
    raw_rows: list[tuple[str, str]] = []
    for step in result.steps:
        reason = step.error or step.skip_reason
        human = _humanize_stage_summary(step.name, step.summary)
        lines.append(
            "| "
            f"{step.name} | {step.status} | {step.elapsed:.1f}s | "
            f"{_clean_cell(human)} | {_clean_cell(reason)} |"
        )
        if (
            step.summary
            and human != step.summary
            and _has_raw_counters(step.summary)
        ):
            raw_rows.append((step.name, step.summary))

    if raw_rows:
        lines.extend(["", "<details>", "<summary>Raw stage counters (디버깅용)</summary>", ""])
        for name, raw in raw_rows:
            lines.append(f"- `{name}`: {raw}")
        lines.extend(["", "</details>"])

    failures = [step for step in result.steps if step.status == StageStatus.FAILED]
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(f"- {step.name}: {step.error}" for step in failures)
    else:
        lines.append("- 없음")

    # Profile Pipeline 통계 — update_profile stage 가 실행됐을 때만.
    if result.profile_meta:
        lines.extend(_render_profile_pipeline_section(result.profile_meta))

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


def _render_profile_pipeline_section(meta: dict[str, object]) -> list[str]:
    """Profile Pipeline 섹션 markdown 라인 (앞 빈 줄 포함).

    update_profile stage 가 실행됐을 때만 호출. promotion/dedupe/dismissed 지표를
    한 화면에서 확인하기 위한 관찰성 블록.
    """
    def _i(key: str) -> int:
        v = meta.get(key, 0)
        return int(v) if isinstance(v, int) else 0

    lines = [
        "",
        "## Profile Pipeline",
        "",
        f"- raw 추출: fact {_i('raw_facts')} · pattern {_i('raw_patterns')}",
        f"- promoted (ledger 통과): fact {_i('promoted_facts')} · "
        f"pattern {_i('promoted_patterns')}",
        f"- awaiting (ledger 대기): fact {_i('awaiting_facts')} · "
        f"pattern {_i('awaiting_patterns')}",
        f"- vault dedupe 제거: {_i('vault_dropped')}",
        f"- dismissed index: 활성 {_i('dismissed_total')}, "
        f"만료 재노출 {_i('dismissed_expired')}",
        f"- candidate 저장: fact {_i('candidate_facts')} · "
        f"pattern {_i('candidate_patterns')}",
    ]
    reason_counts_raw = meta.get("dismissed_reason_counts", {})
    if isinstance(reason_counts_raw, dict) and reason_counts_raw:
        lines.extend(["", "### dismissed reason 분포", ""])
        items = sorted(
            ((str(k), int(v) if isinstance(v, int) else 0)
             for k, v in reason_counts_raw.items()),
            key=lambda x: (-x[1], x[0]),
        )
        for reason, count in items:
            label = reason or "(미상)"
            lines.append(f"- {label}: {count}")
    return lines


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


# ---------------------------------------------------------------------------
# Summary humanization
# ---------------------------------------------------------------------------
#
# 각 stage 의 raw summary 문자열을 사람이 읽기 좋은 한 문장으로 변환한다.
# 변환 실패하거나 알 수 없는 stage 면 raw 를 그대로 둔다 (회귀 시 디버깅 보전).


def _format_bytes(num: int) -> str:
    """바이트 수를 사람용 단위(B / KB / MB / GB)로 변환."""
    n = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{num} B"


def _parse_kv(raw: str) -> dict[str, int]:
    """`key=value` / `key+=value` 토큰을 dict 로 파싱. value 정수만."""
    import re

    out: dict[str, int] = {}
    for m in re.finditer(r"(\w+)\+?=(\d+)", raw):
        out[m.group(1)] = int(m.group(2))
    return out


def _humanize_stage_summary(stage: str, raw: str) -> str:
    """Stage 별 raw summary → 사람 친화 문장. 알 수 없으면 raw 그대로."""
    if not raw:
        return raw
    if stage in (
        "collect_claude_code",
        "collect_codex",
        "collect_aider",
    ):
        labels = {
            "collect_claude_code": "Claude 활동 로그",
            "collect_codex": "Codex 활동 로그",
            "collect_aider": "Aider 대화",
        }
        label = labels[stage]
        kv = _parse_kv(raw)
        if "mirrored" in kv:
            parts = [f"{label} {kv['mirrored']}개 mirror"]
            if kv.get("bytes", 0) > 0:
                parts.append(f"({_format_bytes(kv['bytes'])})")
            extras: list[str] = []
            if kv.get("truncations", 0):
                extras.append(f"잘림 {kv['truncations']}")
            if kv.get("skipped_empty", 0):
                extras.append(f"빈 파일 {kv['skipped_empty']}")
            if kv.get("errors", 0):
                extras.append(f"에러 {kv['errors']}")
            if extras:
                parts.append("· " + ", ".join(extras))
            return " ".join(parts)
    elif stage in (
        "collect_cursor",
        "collect_continue",
        "collect_day_one",
    ):
        labels = {
            "collect_cursor": "Cursor DB",
            "collect_continue": "Continue.dev 세션",
            "collect_day_one": "Day One DB",
        }
        label = labels[stage]
        kv = _parse_kv(raw)
        if "mirrored" in kv:
            parts = [f"{label} {kv['mirrored']}개 mirror"]
            if kv.get("bytes", 0) > 0:
                parts.append(f"({_format_bytes(kv['bytes'])})")
            extras = []
            if kv.get("unchanged", 0):
                extras.append(f"변경 없음 {kv['unchanged']}")
            if kv.get("errors", 0):
                extras.append(f"에러 {kv['errors']}")
            if extras:
                parts.append("· " + ", ".join(extras))
            return " ".join(parts)
    elif stage == "collect_gmail_sent":
        if raw.strip() == "disabled":
            return "Gmail Sent — opt-out (SYNAPSE_GMAIL_ENABLE 미설정)"
        kv = _parse_kv(raw)
        if "added" in kv:
            parts = [
                f"Gmail Sent {kv.get('added', 0)}개 mirror "
                f"(목록 {kv.get('listed', 0)}개)"
            ]
            if kv.get("bytes", 0) > 0:
                parts.append(f"({_format_bytes(kv['bytes'])})")
            if kv.get("errors", 0):
                parts.append(f"· 에러 {kv['errors']}")
            return " ".join(parts)
    elif stage == "collect_obsidian":
        kv = _parse_kv(raw)
        if "mirrored" in kv:
            parts = [f"vault 노트 {kv['mirrored']}개 mirror"]
            if kv.get("bytes", 0) > 0:
                parts.append(f"({_format_bytes(kv['bytes'])})")
            extras = []
            if kv.get("unchanged", 0):
                extras.append(f"변경 없음 {kv['unchanged']}")
            if kv.get("cutoff_skip", 0):
                extras.append(f"cutoff skip {kv['cutoff_skip']}")
            if kv.get("errors", 0):
                extras.append(f"에러 {kv['errors']}")
            if extras:
                parts.append("· " + ", ".join(extras))
            return " ".join(parts)
    elif stage == "update_profile":
        kv = _parse_kv(raw)
        if "fact" in kv or "pattern" in kv:
            parts = [
                f"Fact {kv.get('fact', 0)}개, Pattern {kv.get('pattern', 0)}개"
            ]
            if "→" in raw:
                tail = raw.split("→", 1)[1].strip()
                if tail:
                    parts.append(f"→ {tail}")
            return " ".join(parts)
    # classify / generate / report 는 이미 한국어 사람 친화 — 그대로
    return raw


def _has_raw_counters(raw: str) -> bool:
    """raw 가 key=value 카운터를 포함하면 details 블록 가치 있음."""
    return "=" in raw


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
    acquire_lock: bool = True,
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
            wiki/card write 동시성 회피를 위해 quick + full 동시 실행 금지.
        quick_days: ``quick=True`` 일 때 mtime cutoff 일수. 기본 7.
        quick_max_clusters: ``quick=True`` 일 때 classify 최대 cluster 수. 기본 10.
        dry_run: True면 단계 이름만 출력.
        stage_actions: stage body override (테스트용).
        on_log: print 대체 (테스트용).
    """
    validate_daily_stages()
    _validate_stage_names("only", only)
    _validate_stage_names("skip", skip)
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

    lock_context = (
        DailyRunLock()
        if acquire_lock and status_sink is None
        else contextlib.nullcontext()
    )

    with lock_context:
        return _run_daily_unlocked(
            result=result,
            selected=selected,
            resume_from=resume_from,
            classify_model=classify_model,
            generate_model=generate_model,
            profile_model=profile_model,
            profile_sample_lines=profile_sample_lines,
            profile_facts_only=profile_facts_only,
            quick=quick,
            quick_days=quick_days,
            quick_max_clusters=quick_max_clusters,
            stage_actions=stage_actions,
            on_log=on_log,
            status_sink=status_sink,
            t_start=t_start,
        )


def _run_daily_unlocked(
    *,
    result: DailyResult,
    selected: set[str],
    resume_from: str | None,
    classify_model: str,
    generate_model: str,
    profile_model: str,
    profile_sample_lines: int,
    profile_facts_only: bool,
    quick: bool,
    quick_days: int,
    quick_max_clusters: int,
    stage_actions: Mapping[str, StageAction] | None,
    on_log: Callable[[str], None],
    status_sink: StatusSink | None,
    t_start: float,
) -> DailyResult:
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
        result=result,
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
                step_result = _run_report_step(result, t_start=t_start, on_log=on_log)
            else:
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
