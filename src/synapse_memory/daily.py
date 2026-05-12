"""일일 자동 파이프라인 — 5분 안에 끝나는 통합 워크플로.

Steps (incremental — 이미 처리된 건 자동 skip)::

    1. collect claude-code           (mirror 새 줄만)
    2. collect obsidian              (변경 .md만)
    3. cluster classify --resume     (새 cluster만)
    4. card generate (--force=False) (새 cluster만 Card 생성)
    5. rag index                     (Card upsert)
    6. me update-profile             (오늘 활동 분석 → MemoryInbox PR)

--only로 일부 단계만 건너뛰기. --dry-run으로 단계만 출력.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 단계 이름 — CLI --only에서 사용
STEPS = (
    "collect_claude_code",
    "collect_obsidian",
    "classify",
    "generate",
    "index",
    "update_profile",
)


@dataclass
class StepResult:
    name: str
    elapsed: float
    summary: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class DailyResult:
    steps: list[StepResult] = field(default_factory=list)
    total_elapsed: float = 0.0

    @property
    def errors(self) -> int:
        return sum(1 for s in self.steps if s.error)


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
        return StepResult(name=name, elapsed=elapsed, error=str(exc))
    elapsed = time.monotonic() - t0
    on_log(f"  ({elapsed:.1f}s) {summary}")
    return StepResult(name=name, elapsed=elapsed, summary=str(summary))


def run_daily(
    *,
    only: set[str] | None = None,
    skip: set[str] | None = None,
    classify_model: str = "haiku",
    generate_model: str = "sonnet",
    profile_model: str = "sonnet",
    profile_sample_lines: int = 200,
    profile_facts_only: bool = False,
    dry_run: bool = False,
    on_log: Callable[[str], None] = print,
) -> DailyResult:
    """일일 파이프라인 실행.

    Args:
        only: 이 단계 이름들만 실행. None이면 전체.
        skip: 제외할 단계.
        classify_model / generate_model / profile_model: 단계별 AI 모델.
        profile_sample_lines: update-profile의 history 분석 줄 수.
        profile_facts_only: DecisionPattern 추출 skip.
        dry_run: True면 단계 이름만 출력.
        on_log: print 대체 (테스트용).
    """
    result = DailyResult()
    t_start = time.monotonic()

    selected = set(only) if only else set(STEPS)
    if skip:
        selected -= set(skip)

    if dry_run:
        on_log("[DRY RUN] 실행 단계:")
        for s in STEPS:
            mark = "  [x]" if s in selected else "  [ ]"
            on_log(f"{mark} {s}")
        return result

    # 1. collect claude-code
    if "collect_claude_code" in selected:
        from synapse_memory.collectors.claude_code import collect_claude_code

        def step():
            stats = collect_claude_code()
            return stats.summary()

        result.steps.append(_run_step("collect_claude_code", step, on_log=on_log))

    # 2. collect obsidian
    if "collect_obsidian" in selected:
        from synapse_memory.collectors.obsidian import collect_obsidian

        def step():
            stats = collect_obsidian()
            return stats.summary()

        result.steps.append(_run_step("collect_obsidian", step, on_log=on_log))

    # 3. classify (new clusters only)
    if "classify" in selected:
        from synapse_memory.cards.auto_classify import (
            classify_cluster,
            load_classifications,
            save_classifications,
        )
        from synapse_memory.clusters import identify_clusters
        from synapse_memory.collectors.obsidian import get_vault_path as obs_path
        from synapse_memory.llm import detect_ai_environment

        def step():
            env = detect_ai_environment(model=classify_model)
            if not env.ready:
                raise RuntimeError("AI provider 미설치")
            clusters = identify_clusters()
            existing = load_classifications()
            new_clusters = [c for c in clusters if c.cluster_id not in existing]
            if not new_clusters:
                return "신규 cluster 없음"
            obs_root = obs_path()
            cls_dict = dict(existing)
            for c in new_clusters:
                try:
                    cls = classify_cluster(
                        c, obs_root=obs_root, ai_env=env, model=classify_model
                    )
                    cls_dict[c.cluster_id] = cls
                except Exception as exc:
                    on_log(f"    {c.cluster_id} 실패: {exc}")
            save_classifications(cls_dict)
            return f"신규 {len(new_clusters)}개 분류"

        result.steps.append(_run_step("classify", step, on_log=on_log))

    # 4. card generate (project/company kind, skip existing)
    if "generate" in selected:
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

        def step():
            env = detect_ai_environment(model=generate_model)
            if not env.ready:
                raise RuntimeError("AI provider 미설치")
            classifications = load_classifications()
            if not classifications:
                return "classifications 비어있음"
            clusters = {c.cluster_id: c for c in identify_clusters()}
            obs_root = obs_path()
            created = 0
            for cid, cls in classifications.items():
                if cls.kind not in ("project", "company"):
                    continue
                if cid not in clusters:
                    continue
                if cls.kind == "project":
                    target = projects_dir() / f"{cid}.md"
                    if target.exists():
                        continue
                    try:
                        card = generate_project_card(
                            clusters[cid],
                            candidate_name=cls.candidate_name,
                            obs_root=obs_root,
                            ai_env=env,
                            model=generate_model,
                        )
                        save_project_card(card)
                        created += 1
                    except Exception as exc:
                        on_log(f"    {cid} 실패: {exc}")
                else:
                    target = companies_dir() / f"{cid}.md"
                    if target.exists():
                        continue
                    try:
                        card_c = generate_company_card(
                            clusters[cid],
                            candidate_name=cls.candidate_name,
                            obs_root=obs_root,
                            ai_env=env,
                            model=generate_model,
                        )
                        save_company_card(card_c)
                        created += 1
                    except Exception as exc:
                        on_log(f"    {cid} 실패: {exc}")
            return f"신규 Card {created}개 생성"

        result.steps.append(_run_step("generate", step, on_log=on_log))

    # 5. rag index (upsert)
    if "index" in selected:
        from synapse_memory.rag import index_cards

        def step():
            stats = index_cards()
            return (
                f"project={stats.project_cards} company={stats.company_cards}"
            )

        result.steps.append(_run_step("index", step, on_log=on_log))

    # 6. update profile (today's history → MemoryInbox PR)
    if "update_profile" in selected:
        from synapse_memory.llm import detect_ai_environment
        from synapse_memory.profile.extract import (
            extract_decision_patterns,
            extract_profile_facts,
            save_profile_update,
        )

        def step():
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

        result.steps.append(_run_step("update_profile", step, on_log=on_log))

    result.total_elapsed = time.monotonic() - t_start
    return result
