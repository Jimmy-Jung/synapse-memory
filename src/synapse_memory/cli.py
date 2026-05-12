"""synapse-memory CLI 진입점.

현재 명령:
    synapse-memory doctor                       환경 진단 + L0 setup
    synapse-memory collect claude-code          Claude Code 로그 → L0 mirror
    synapse-memory collect obsidian             Obsidian vault → L0 mirror
    synapse-memory redact backfill claude-code  L0 raw → redacted/ (Pass 1+2)
    synapse-memory eval golden                  골든셋 정확도 측정 (P/R/F1)
    synapse-memory card list                    Project Card 목록
    synapse-memory card show <id>               Project Card 내용
    synapse-memory card new <id> <name>         Project Card 빈 템플릿 생성
    synapse-memory cluster scan                 raw → 프로젝트 클러스터
    synapse-memory cluster classify             cluster → kind (Claude Code CLI)

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import os
import stat
import sys
import time
from pathlib import Path

from synapse_memory import __version__
from synapse_memory.cards import (
    CompanyCard,
    ProjectCard,
    list_company_cards,
    list_project_cards,
    load_company_card,
    load_project_card,
    save_company_card,
    save_project_card,
    serialize_company_card,
    serialize_project_card,
)
from synapse_memory.cards.auto_classify import (
    classify_cluster,
    load_classifications,
    save_classifications,
)
from synapse_memory.cards.auto_generate import (
    generate_company_card,
    generate_project_card,
)
from synapse_memory.cards.company import companies_dir
from synapse_memory.cards.project import projects_dir
from synapse_memory.clusters import identify_clusters
from synapse_memory.collectors.claude_code import (
    DEFAULT_CLAUDE_HOME,
    collect_claude_code,
)
from synapse_memory.collectors.obsidian import (
    collect_obsidian,
    get_vault_path,
)
from synapse_memory.collectors.obsidian import get_vault_path as get_obsidian_vault
from synapse_memory.cost.events import command_context
from synapse_memory.cost.summary import (
    load_summary,
    render_summary_json,
    render_summary_table,
)
from synapse_memory.daily import STEPS, run_daily
from synapse_memory.endpoints.ask import ask
from synapse_memory.endpoints.me import (
    decide,
    draft_resume,
    what_did_i_think,
)
from synapse_memory.eval.golden import (
    default_synthetic_path,
    evaluate,
    load_golden_set,
)
from synapse_memory.feedback.events import append_feedback_event, build_feedback_event
from synapse_memory.feedback.targets import (
    resolve_card_target,
    resolve_last_answer_targets,
    resolve_pattern_target,
)
from synapse_memory.llm import AIError, detect_ai_environment
from synapse_memory.llm.apfel import MIN_MACOS_MAJOR, detect_environment
from synapse_memory.profile.extract import (
    extract_decision_patterns,
    extract_profile_facts,
    save_profile_update,
)
from synapse_memory.rag import (
    embed_query,
    index_cards,
    open_vector_store,
)
from synapse_memory.rag.embeddings import (
    EmbeddingError,
    EmbeddingUnavailableError,
)
from synapse_memory.rag.vector_store import VectorStoreError
from synapse_memory.redaction import redact_full
from synapse_memory.redaction.redactlist import (
    add_redactlist_item,
    load_redactlist,
    remove_redactlist_item,
)
from synapse_memory.storage.l0 import (
    L0_DIR_MODE,
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)
from synapse_memory.storage.last_response import load_last_answer

OK = "✓"
FAIL = "✗"

# 대화형 endpoint(ask / me *) 가 사람-터미널에서 직접 호출되었을 때 안내하는 경고.
# Claude Code / Codex 의 slash 명령이 subprocess 로 호출하면 SYNAPSE_FROM_AGENT=1 환경변수가
# 설정되어 있어 경고가 생략됩니다. stdout 이 pipe 인 경우(자동화)도 통과.
_INTERACTIVE_GUARD_DELAY_SECONDS = 3
_INTERACTIVE_GUARD_MESSAGE = (
    "⚠  {command} 는 LLM 대화 컨텍스트에서 호출할 때 가장 자연스럽게 동작합니다.\n"
    "   Claude Code / Codex 안에서 `/synapse-{slash}` 슬래시 명령으로 호출하면\n"
    "   결과가 대화에 인라인되고 후속 질문에 컨텍스트가 유지됩니다.\n"
    "   계속 진행하려면 {delay}초 기다리세요. 즉시 우회: SYNAPSE_FROM_AGENT=1\n"
)


def _stdout_is_tty() -> bool:
    """sys.stdout.isatty() 의 thin wrapper — 테스트에서 monkeypatch 하기 위함."""
    return sys.stdout.isatty()


def _interactive_guard(command: str, slash: str) -> None:
    """대화형 endpoint 에서 사람의 직접 CLI 호출을 부드럽게 만류한다."""
    if os.environ.get("SYNAPSE_FROM_AGENT"):
        return
    if not _stdout_is_tty():
        return
    sys.stderr.write(
        _INTERACTIVE_GUARD_MESSAGE.format(
            command=command, slash=slash, delay=_INTERACTIVE_GUARD_DELAY_SECONDS
        )
    )
    sys.stderr.flush()
    time.sleep(_INTERACTIVE_GUARD_DELAY_SECONDS)


def cmd_doctor(_args: argparse.Namespace) -> int:
    """환경 진단 — apfel/macOS/Apple Silicon."""
    env = detect_environment()

    print("Synapse Memory 환경 진단")
    print("=" * 44)

    # apfel
    if env.apfel_path is not None:
        print(f"{OK} apfel 설치: {env.apfel_path}")
        if env.apfel_version:
            print(f"  버전: {env.apfel_version}")
    else:
        print(f"{FAIL} apfel 미설치")
        print("  설치: brew install Arthur-Ficial/tap/apfel")

    # Apple Silicon
    if env.is_apple_silicon:
        print(f"{OK} Apple Silicon (arm64)")
    else:
        print(f"{FAIL} Apple Silicon 아님 — FoundationModels 사용 불가")

    # macOS
    major = env.macos_major
    if major is not None and major >= MIN_MACOS_MAJOR:
        print(f"{OK} macOS {env.macos_version} (Tahoe+)")
    elif major is not None:
        print(f"{FAIL} macOS {env.macos_version} — Tahoe(26)+ 필요")
    else:
        print(f"{FAIL} macOS 버전 확인 실패: {env.macos_version!r}")

    # L0 setup — ~/.synapse/private 디렉토리 생성 + 권한 0700 강제
    l0 = ensure_l0_root_secure()
    actual_mode = stat.S_IMODE(os.stat(l0).st_mode)
    if actual_mode == L0_DIR_MODE:
        print(f"{OK} L0 루트: {l0} (0{L0_DIR_MODE:o})")
    else:
        print(f"{FAIL} L0 루트 권한 갱신 실패: {l0} (현재 0{actual_mode:o})")

    # AI provider CLI
    ai_env = detect_ai_environment()
    if ai_env.ready:
        ver = ai_env.version or "(version unknown)"
        print(
            f"{OK} AI provider ({ai_env.provider}): {ai_env.path} [{ver}] "
            f"(model={ai_env.model})"
        )
    else:
        print(f"{FAIL} AI provider ({ai_env.provider}) 사용 불가")
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}")

    print("=" * 44)
    if env.ready:
        print("✓ 준비 완료")
        return 0

    print("환경 미충족:")
    for reason in env.reasons_unavailable():
        print(f"  - {reason}")
    return 1


def cmd_card_list(args: argparse.Namespace) -> int:
    """Project / Company Card 목록."""
    kind = args.type
    shown = 0

    if kind in ("project", "all"):
        cards = list_project_cards()
        if cards:
            print(f"\n[Project Cards]   {projects_dir()}")
            print(
                f"{'ID':<25} {'STATUS':<12} {'ROLE':<25} {'PERIOD':<20}"
            )
            print("-" * 85)
            for c in cards:
                period = c.period_start or ""
                if c.period_end:
                    period = f"{period} ~ {c.period_end}"
                print(
                    f"{c.project_id:<25} {c.status:<12} "
                    f"{(c.role or '')[:24]:<25} {period:<20}"
                )
            shown += len(cards)

    if kind in ("company", "all"):
        cards_c = list_company_cards()
        if cards_c:
            print(f"\n[Company Cards]   {companies_dir()}")
            print(
                f"{'ID':<25} {'STATUS':<14} {'COUNTRY':<8} {'POSITIONS':<5}"
            )
            print("-" * 85)
            for c in cards_c:
                print(
                    f"{c.company_id:<25} {c.status:<14} "
                    f"{(c.country or ''):<8} {len(c.positions):<5}"
                )
            shown += len(cards_c)

    if shown == 0:
        print(f"Card 0개 (type={kind})")
    else:
        print(f"\n총 {shown}개")
    return 0


def cmd_card_show(args: argparse.Namespace) -> int:
    """Card 내용 출력."""
    cid = args.card_id
    try:
        if args.type == "company":
            card = load_company_card(cid)
            print(serialize_company_card(card))
        else:
            card = load_project_card(cid)
            print(serialize_project_card(card))
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_card_new(args: argparse.Namespace) -> int:
    """빈 Card 템플릿 생성."""
    import datetime

    cid = args.card_id
    today = datetime.date.today().isoformat()

    if args.type == "company":
        target = companies_dir() / f"{cid}.md"
        if target.exists() and not args.force:
            print(f"{FAIL} 이미 존재: {target}", file=sys.stderr)
            return 1
        card_c = CompanyCard(
            company_id=cid,
            display_name=args.display_name,
            status="target",
            created=today,
            last_reviewed=today,
            body=(
                "## 회사 개요\n\n\n"
                "## 기술 스택\n\n\n"
                "## 문화\n\n\n"
                "## 매칭되는 내 프로젝트\n\n\n"
                "## 메모\n"
            ),
        )
        path = save_company_card(card_c)
    else:
        target = projects_dir() / f"{cid}.md"
        if target.exists() and not args.force:
            print(f"{FAIL} 이미 존재: {target}", file=sys.stderr)
            return 1
        card_p = ProjectCard(
            project_id=cid,
            display_name=args.display_name,
            status="active",
            created=today,
            last_reviewed=today,
            body=(
                "## 문제\n\n\n"
                "## 접근\n\n\n"
                "## 영향\n\n\n"
                "## 기술 결정\n\n\n"
                "## 회고\n"
            ),
        )
        path = save_project_card(card_p)

    print(f"{OK} 생성: {path}")
    return 0


def cmd_rag_index(args: argparse.Namespace) -> int:
    """모든 Card를 벡터 DB에 인덱싱."""
    print(f"인덱싱 시작 (rebuild={args.rebuild})")
    try:
        store = open_vector_store()

        def _progress(stage: str, current: int, total: int) -> None:
            if current == 1:
                print(f"  [{stage}] {total}개 임베딩 중...")

        stats = index_cards(
            store=store, rebuild=args.rebuild, on_progress=_progress
        )
    except (EmbeddingUnavailableError, VectorStoreError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except EmbeddingError as exc:
        print(f"{FAIL} 임베딩 실패: {exc}", file=sys.stderr)
        return 1

    print(
        f"\n인덱싱 완료: project={stats.project_cards} "
        f"company={stats.company_cards} "
        f"bytes={stats.bytes_indexed}"
    )
    print(f"총 벡터: {open_vector_store().count()}")
    if stats.failed:
        for stage, msg in stats.failed:
            print(f"  실패: {stage} — {msg}", file=sys.stderr)
        return 1
    return 0


def cmd_me_what_did_i_think(args: argparse.Namespace) -> int:
    _interactive_guard("me what-did-i-think", "recall")

    # FR-009 — --timeline + --by distance 충돌 검증
    timeline_flag = bool(getattr(args, "timeline", False))
    by_arg = getattr(args, "by", None)
    if timeline_flag and by_arg == "distance":
        print(
            "error: --timeline and --by distance conflict — pick one.",
            file=sys.stderr,
        )
        return 1
    if timeline_flag or by_arg == "time":
        effective_by = "time"
    elif by_arg == "distance":
        effective_by = "distance"
    else:
        effective_by = "distance"  # 기본 (FR-013 회귀 가드)

    # FR-010 — --limit 범위 검증
    limit = int(getattr(args, "limit", 20))
    if not (1 <= limit <= 100):
        print(f"error: --limit must be in [1, 100], got {limit}", file=sys.stderr)
        return 2

    # Claude 환경은 distance 모드에만 필수 (timeline 은 외부 LLM 미호출)
    ai_env = None
    if effective_by == "distance":
        ai_env = detect_ai_environment(model=args.model)
        if not ai_env.ready:
            print(f"{FAIL} AI provider 사용 불가", file=sys.stderr)
            return 2
    try:
        result = what_did_i_think(
            args.topic,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
            by=effective_by,  # type: ignore[arg-type]
            limit=limit,
        )
    except (EmbeddingUnavailableError, VectorStoreError, AIError, ValueError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    print(f"주제: {result.topic}\n")
    print(result.answer)
    print()
    print("=" * 60)
    print(f"출처 ({len(result.source_ids)}):")
    for cid in result.source_ids:
        print(f"  - {cid}")
    return 0


def cmd_me_decide(args: argparse.Namespace) -> int:
    _interactive_guard("me decide", "decide")
    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가", file=sys.stderr)
        return 2
    try:
        result = decide(
            args.situation,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
        )
    except (EmbeddingUnavailableError, VectorStoreError, AIError, ValueError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    print(f"상황: {result.situation}")
    profile_note = "Profile/Patterns 사용 ✓" if result.profile_used else "Profile 없음 (일반 모드)"
    print(f"({profile_note})\n")
    print(result.answer)
    print()
    print("=" * 60)
    print(f"참고 Card ({len(result.source_ids)}):")
    for cid in result.source_ids:
        print(f"  - {cid}")
    return 0


def cmd_daily(args: argparse.Namespace) -> int:
    """일일 통합 파이프라인."""
    only = set(args.only.split(",")) if args.only else None
    skip = set(args.skip.split(",")) if args.skip else None

    result = run_daily(
        only=only,
        skip=skip,
        classify_model=args.classify_model,
        generate_model=args.generate_model,
        profile_model=args.profile_model,
        profile_sample_lines=args.profile_sample_lines,
        profile_facts_only=args.profile_facts_only,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        return 0

    print("\n" + "=" * 60)
    print(f"Daily 총 시간: {result.total_elapsed:.1f}s")
    print(f"실행 단계: {len(result.steps)}, 실패: {result.errors}")
    for s in result.steps:
        status = OK if s.ok else FAIL
        print(f"  {status} {s.name:<22} {s.elapsed:>6.1f}s  {s.summary or s.error}")
    return 1 if result.errors else 0


def cmd_me_update_profile(args: argparse.Namespace) -> int:
    """raw → Profile/DecisionPattern 후보 → MemoryInbox PR."""
    _interactive_guard("me update-profile", "update-profile")
    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    try:
        print(f"ProfileFact 추출 중 (sample={args.sample_lines})...")
        facts = extract_profile_facts(
            sample_lines=args.sample_lines,
            model=args.model,
            ai_env=ai_env,
        )
        print(f"  → {len(facts)} fact 추출")

        patterns = []
        if not args.facts_only:
            print("DecisionPattern 추출 중...")
            patterns = extract_decision_patterns(
                sample_lines=args.sample_lines,
                model=args.model,
                ai_env=ai_env,
            )
            print(f"  → {len(patterns)} pattern 추출")
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except AIError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    path = save_profile_update(facts, patterns)
    print(f"\n{OK} MemoryInbox PR 저장: {path}")
    print("  검토 후 vault 90_System/AI/Profile.md, DecisionPatterns.md 반영")
    return 0


def cmd_me_draft_resume(args: argparse.Namespace) -> int:
    """회사 맞춤 이력서 자동 생성 → vault Drafts."""
    _interactive_guard("me draft-resume", "resume")
    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    try:
        result = draft_resume(
            args.company_id,
            top_k_projects=args.top_k,
            model=args.model,
            ai_env=ai_env,
        )
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except (EmbeddingUnavailableError, VectorStoreError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except (EmbeddingError, AIError, ValueError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    print(f"{OK} 이력서 생성: {result.saved_path}")
    print(f"  매칭 ProjectCard ({len(result.project_card_ids)}):")
    for pid in result.project_card_ids:
        print(f"    - {pid}")
    return 0


def _parse_input_kv(items: list[str]) -> dict[str, str]:
    """``--input key=value`` 들을 dict 로 변환."""
    out: dict[str, str] = {}
    for raw in items or []:
        if "=" not in raw:
            raise ValueError(f"--input must be key=value, got '{raw}'")
        k, _, v = raw.partition("=")
        k = k.strip()
        if not k:
            raise ValueError(f"--input key empty: '{raw}'")
        out[k] = v
    return out


def cmd_me_generate(args: argparse.Namespace) -> int:
    """Recipe-based generator (007-me-recipes) — me generate <recipe>."""
    from synapse_memory.recipes import (
        InputValidationError,
        RecipeNotFoundError,
        RecipePromptTooLargeError,
        RecipeValidationError,
        generate as recipes_generate,
    )

    _interactive_guard(f"me generate {args.recipe}", f"generate-{args.recipe}")

    try:
        inputs = _parse_input_kv(args.input or [])
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    vault_path = Path(args.vault).expanduser().resolve() if args.vault else None
    today_resolved: datetime.date | None
    if args.today:
        try:
            today_resolved = datetime.date.fromisoformat(args.today)
        except ValueError as exc:
            print(f"{FAIL} --today must be YYYY-MM-DD: {exc}", file=sys.stderr)
            return 1
    else:
        today_resolved = None

    store = None
    try:
        store = open_vector_store()
    except (VectorStoreError, EmbeddingUnavailableError):
        store = None  # recipe 가 RAG 없이도 동작 가능

    t0 = time.monotonic()
    try:
        result = recipes_generate(
            args.recipe,
            inputs=inputs,
            vault_path=vault_path,
            store=store,
            today=today_resolved,
            cli_language=args.language,
            cli_domain=args.domain,
            dry_run=args.dry_run,
        )
    except RecipeNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except InputValidationError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 3
    except (RecipeValidationError, RecipePromptTooLargeError) as exc:
        print(f"{FAIL} recipe 검증 실패: {exc}", file=sys.stderr)
        return 4
    except (EmbeddingError, AIError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 10

    duration_ms = int((time.monotonic() - t0) * 1000)
    sys.stdout.write(result.answer_markdown.rstrip() + "\n")
    if result.saved_path:
        sys.stdout.write(f"\n[saved] {result.saved_path}\n")
    sys.stdout.flush()
    sys.stderr.write(
        f"[me.generate.{result.recipe_name}] "
        f"locale={result.locale_source}:{result.locale} "
        f"domain={result.domain_source}:{result.domain} "
        f"profile_used={result.profile_used} "
        f"matched={len(result.source_ids)} "
        f"duration={duration_ms}ms\n"
    )
    sys.stderr.flush()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """자연어 질의 → RAG → AI 답변."""
    _interactive_guard("ask", "ask")
    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    where = None
    if args.kind:
        where = {"source_kind": f"card_{args.kind}"}

    try:
        result = ask(
            args.query,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
            where=where,
        )
    except (EmbeddingUnavailableError, VectorStoreError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except (EmbeddingError, AIError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    print(f"질문: {result.query}\n")
    print(result.answer)
    print()
    print("=" * 60)
    print(f"출처 ({len(result.sources)}):")
    for s in result.sources:
        print(
            f"  [{s.distance:.3f}] {s.source_kind:<14} {s.card_id} "
            f"— {s.display_name}"
        )
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    """사용자 피드백 기록."""
    try:
        action = _feedback_action(args)
        if action == "reject" and not str(args.reject or "").strip():
            raise ValueError("reject feedback reason is required")
        targets = _feedback_targets(args)
        if not targets:
            print("No feedback targets resolved.", file=sys.stderr)
            return 1

        events = []
        last_ref = load_last_answer() if args.feedback_target == "last" else None
        for target in targets:
            events.append(
                build_feedback_event(
                    target_kind=target.target_kind,  # type: ignore[arg-type]
                    target_ref=target.target_ref,
                    action=action,
                    reason=args.reject,
                    weight=args.weight,
                    answer_id_context=last_ref.answer_id if last_ref else None,
                )
            )
        for event in events:
            append_feedback_event(event)
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{FAIL} feedback 저장 실패: {exc}", file=sys.stderr)
        return 2

    target_label = (
        f"last answer {last_ref.answer_id}" if args.feedback_target == "last" and last_ref
        else f"{args.feedback_target} {args.target_ref}"
    )
    print(
        f"{OK} Recorded {action} for {target_label} "
        f"(targets={len(events)}, weight={events[0].weight:+.2f})"
    )
    refs = ", ".join(e.target_ref for e in events)
    print(f"  → next index will apply updated feedback_score: {refs}")
    return 0


def cmd_cost_summary(args: argparse.Namespace) -> int:
    """최근 cost event 집계."""
    if args.days < 1:
        print("--days must be >= 1", file=sys.stderr)
        return 1
    try:
        summary = load_summary(days=args.days, by=args.by)
    except (OSError, ValueError) as exc:
        print(f"{FAIL} cost summary 실패: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(render_summary_json(summary))
    else:
        print(render_summary_table(summary))
    return 0


def _feedback_action(args: argparse.Namespace) -> str:
    actions = [
        bool(args.accept),
        bool(args.reject is not None),
        bool(args.weight is not None),
    ]
    if sum(actions) != 1:
        raise ValueError("exactly one of --accept, --reject, --weight is required")
    if args.accept:
        return "accept"
    if args.reject is not None:
        return "reject"
    return "weight"


def _feedback_targets(args: argparse.Namespace):
    vault_path = Path(args.vault_path).expanduser() if args.vault_path else None
    if args.feedback_target == "last":
        last_ref = load_last_answer()
        if last_ref is None:
            raise ValueError("No recent answer found. Run ask/me first, then retry feedback last.")
        return resolve_last_answer_targets(last_ref)
    if args.feedback_target == "card":
        return [resolve_card_target(str(args.target_ref), vault_path=vault_path)]
    if args.feedback_target == "pattern":
        return [resolve_pattern_target(str(args.target_ref), vault_path=vault_path)]
    raise ValueError(f"unknown feedback target: {args.feedback_target}")


def cmd_rag_search(args: argparse.Namespace) -> int:
    """벡터 DB 검색 — dense (bge-m3 cosine)."""
    try:
        q_vec = embed_query(args.query)
        store = open_vector_store()
        results = store.query(q_vec, top_k=args.top_k)
    except (EmbeddingUnavailableError, VectorStoreError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except EmbeddingError as exc:
        print(f"{FAIL} 임베딩 실패: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("결과 없음 — `synapse-memory rag index` 먼저 실행")
        return 0

    print(f"쿼리: {args.query!r}  (top {args.top_k}, 거리 작을수록 가까움)")
    print("-" * 80)
    for rec, dist in results:
        name = rec.metadata.get("display_name", rec.id)
        kind = rec.metadata.get("source_kind", "?")
        feedback_score = rec.metadata.get("feedback_score")
        feedback_label = (
            f" feedback={float(feedback_score):.2f}"
            if isinstance(feedback_score, (float, int))
            else ""
        )
        print(f"  [{dist:.3f}] {kind:<14} {rec.id:<30} {name}{feedback_label}")
        if args.show_snippet:
            snippet = rec.document.replace("\n", " ")[:150]
            print(f"    {snippet}")
    return 0


def cmd_card_generate(args: argparse.Namespace) -> int:
    """classify된 cluster들로 ProjectCard/CompanyCard 자동 생성."""
    ai_env = detect_ai_environment()
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    classifications = load_classifications()
    if not classifications:
        print(f"{FAIL} 분류 결과 없음 — 먼저 `synapse-memory cluster classify`")
        return 2

    obs_root = get_obsidian_vault()
    if not obs_root.is_dir():
        print(f"{FAIL} vault 경로 없음: {obs_root}", file=sys.stderr)
        return 2

    # cluster 다시 식별 (classifications에 source 정보 없으니 다시 매칭)
    clusters = {c.cluster_id: c for c in identify_clusters()}

    # filter by kind
    kinds_to_run: set[str] = (
        {"project", "company"} if args.kind == "all" else {args.kind}
    )

    targets: list[tuple[str, str, str]] = []  # (cluster_id, kind, candidate_name)
    for cid, cls in classifications.items():
        if cls.kind not in kinds_to_run:
            continue
        if cid not in clusters:
            continue
        targets.append((cid, cls.kind, cls.candidate_name))

    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    if not targets:
        print(f"생성 대상 0 (kind={args.kind})")
        return 0

    print(f"Card 생성: {len(targets)}개 (model={args.model})")

    fails: list[tuple[str, str]] = []
    saved_cards: list[Path] = []

    for i, (cid, kind, name) in enumerate(targets, 1):
        cluster = clusters[cid]
        try:
            if kind == "project":
                target_path = projects_dir() / f"{cid}.md"
                if target_path.exists() and not args.force:
                    print(
                        f"[{i}/{len(targets)}] {cid:<25} → skip (이미 존재)"
                    )
                    continue
                card = generate_project_card(
                    cluster,
                    candidate_name=name,
                    obs_root=obs_root,
                    ai_env=ai_env,
                    model=args.model,
                )
                path = save_project_card(card)
            else:
                target_path = companies_dir() / f"{cid}.md"
                if target_path.exists() and not args.force:
                    print(
                        f"[{i}/{len(targets)}] {cid:<25} → skip (이미 존재)"
                    )
                    continue
                card_c = generate_company_card(
                    cluster,
                    candidate_name=name,
                    obs_root=obs_root,
                    ai_env=ai_env,
                    model=args.model,
                )
                path = save_company_card(card_c)

            saved_cards.append(path)
            print(f"[{i}/{len(targets)}] {cid:<25} → {kind} → {path.name}")
        except (AIError, ValueError) as exc:
            fails.append((cid, str(exc)))
            print(
                f"[{i}/{len(targets)}] {cid} — 실패: {exc}",
                file=sys.stderr,
            )

    print(f"\n생성 완료: {len(saved_cards)}/{len(targets)}")
    if fails:
        print(f"실패: {len(fails)}")
    return 1 if fails else 0


def cmd_cluster_classify(args: argparse.Namespace) -> int:
    """모든 cluster를 LLM 분류 → classifications.json 저장."""
    ai_env = detect_ai_environment()
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    clusters = identify_clusters()
    if not clusters:
        print("클러스터 없음 — 먼저 collect")
        return 0

    obs_root = get_obsidian_vault()
    if not obs_root.is_dir():
        print(f"{FAIL} vault 경로 없음: {obs_root}", file=sys.stderr)
        return 2

    existing = load_classifications() if args.resume else {}
    if args.resume:
        clusters = [c for c in clusters if c.cluster_id not in existing]
        print(f"--resume: 기존 {len(existing)} 분류 skip, {len(clusters)}개 남음")

    if args.limit and args.limit > 0:
        clusters = clusters[: args.limit]

    print(f"분류 시작: {len(clusters)} cluster (AI provider 호출)")

    classifications = dict(existing)
    fails: list[tuple[str, str]] = []
    for i, cluster in enumerate(clusters, 1):
        try:
            cls = classify_cluster(
                cluster,
                obs_root=obs_root,
                ai_env=ai_env,
                model=args.model,
            )
            classifications[cls.cluster_id] = cls
            print(
                f"[{i}/{len(clusters)}] {cluster.cluster_id:<25} → "
                f"{cls.kind:<8} ({cls.candidate_name})"
            )
        except AIError as exc:
            fails.append((cluster.cluster_id, str(exc)))
            print(
                f"[{i}/{len(clusters)}] {cluster.cluster_id} — 실패: {exc}",
                file=sys.stderr,
            )

    path = save_classifications(classifications)
    print(f"\n저장: {path}")

    # 분포
    from collections import Counter
    by_kind = Counter(c.kind for c in classifications.values())
    print("\n분포:")
    for kind, n in by_kind.most_common():
        print(f"  {kind}: {n}")

    return 1 if fails else 0


def cmd_cluster_scan(args: argparse.Namespace) -> int:
    """raw mirror 스캔 → 프로젝트 클러스터 식별."""
    clusters = identify_clusters()
    if not clusters:
        print("클러스터 0개. 먼저:")
        print("  synapse-memory collect claude-code")
        print("  synapse-memory collect obsidian")
        return 0

    print(
        f"{'CLUSTER_ID':<25} {'CONF':>5} {'CC':>4} {'OBS':>4} "
        f"{'TAGS':>5} CWD"
    )
    print("-" * 90)
    for c in clusters:
        cwd_preview = ", ".join(sorted(c.cwd_paths))[:40]
        print(
            f"{c.cluster_id[:24]:<25} {c.confidence:>5.2f} "
            f"{len(c.claude_jsonl):>4} {len(c.obsidian_files):>4} "
            f"{len(c.tags):>5} {cwd_preview}"
        )
    print(f"\n총 {len(clusters)}개 클러스터")

    if args.show_details and args.show_details > 0:
        print(f"\n=== 상세 (상위 {args.show_details}) ===")
        for c in clusters[: args.show_details]:
            print(f"\n[{c.cluster_id}] confidence={c.confidence:.2f}")
            print(f"  cwd: {sorted(c.cwd_paths)}")
            print(f"  claude_jsonl ({len(c.claude_jsonl)}):")
            for f in c.claude_jsonl[:5]:
                print(f"    - {f}")
            if len(c.claude_jsonl) > 5:
                print(f"    ... 외 {len(c.claude_jsonl) - 5}개")
            print(f"  obsidian ({len(c.obsidian_files)}):")
            for f in c.obsidian_files[:5]:
                print(f"    - {f}")
            if c.tags:
                print(f"  tags: {sorted(c.tags)}")
    return 0


def cmd_redactlist_show(_args: argparse.Namespace) -> int:
    """현재 redact-list 항목 출력."""
    items = load_redactlist()
    if not items:
        print("(redact-list 비어있음)")
        print("`synapse-memory redactlist add <NAME>`로 추가")
        return 0
    print("Redact-list (case-insensitive 강제 마스킹):")
    for item in items:
        print(f"  - {item}")
    print(f"\n총 {len(items)}개")
    return 0


def cmd_redactlist_add(args: argparse.Namespace) -> int:
    if add_redactlist_item(args.item):
        print(f"{OK} 추가: {args.item!r}")
    else:
        print(f"이미 있음: {args.item!r}")
    return 0


def cmd_redactlist_remove(args: argparse.Namespace) -> int:
    if remove_redactlist_item(args.item):
        print(f"{OK} 제거: {args.item!r}")
    else:
        print(f"항목 없음: {args.item!r}")
        return 1
    return 0


def cmd_eval_golden(args: argparse.Namespace) -> int:
    """골든셋 평가 — precision/recall/F1 카테고리별."""
    path: Path = args.set or default_synthetic_path()
    if not path.exists():
        print(f"{FAIL} 골든셋 파일 없음: {path}", file=sys.stderr)
        return 2

    env = detect_environment()
    if not env.ready:
        print(f"{FAIL} apfel 사용 불가:", file=sys.stderr)
        for r in env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    samples = load_golden_set(path)
    print(f"평가: {len(samples)} samples ← {path.name}")

    def _progress(i: int, total: int) -> None:
        # 매 5개마다 점, 매 25개마다 카운터
        if i % 5 == 0:
            print(".", end="", flush=True)
        if i % 25 == 0:
            print(f"{i}", end="", flush=True)

    t0 = time.monotonic()
    result = evaluate(samples, env=env, on_progress=_progress)
    elapsed = time.monotonic() - t0
    print(f"  ({elapsed:.1f}s)")

    print()
    print(
        f"{'카테고리':<22} {'TP':>4} {'FP':>4} {'FN':>4} "
        f"{'P':>6} {'R':>6} {'F1':>6}"
    )
    print("-" * 60)
    for cat, m in sorted(result.per_category.items()):
        print(
            f"{cat:<22} {m.tp:>4} {m.fp:>4} {m.fn:>4} "
            f"{m.precision:>6.2f} {m.recall:>6.2f} {m.f1:>6.2f}"
        )
    print("-" * 60)
    o = result.overall
    print(
        f"{'OVERALL':<22} {o.tp:>4} {o.fp:>4} {o.fn:>4} "
        f"{o.precision:>6.2f} {o.recall:>6.2f} {o.f1:>6.2f}"
    )

    print(
        f"\n완벽한 sample: {result.samples_perfect}/{result.samples_total} "
        f"({result.samples_perfect / result.samples_total * 100:.1f}%)"
    )

    if args.show_failures and result.failures:
        limit = args.show_failures
        print(f"\n=== 실패 sample {len(result.failures)} (처음 {limit}) ===")
        for f in result.failures[:limit]:
            print(f"\n[{f.sample_id}] {f.text!r}")
            for c, v in f.fp:
                print(f"  +FP {c}: {v!r}")
            for c, v in f.fn:
                print(f"  -FN {c}: {v!r}")

    return 0


def cmd_redact_backfill_claude_code(args: argparse.Namespace) -> int:
    """L0 mirror된 Claude Code raw에 redact_full 적용 → redacted/ 저장."""
    src_root = (l0_root() / "raw" / "claude-code").expanduser().resolve()
    dst_root = (l0_root() / "redacted" / "claude-code").expanduser().resolve()

    if not src_root.is_dir():
        print(f"{FAIL} 백필 소스 없음: {src_root}", file=sys.stderr)
        print(
            "먼저 `synapse-memory collect claude-code` 실행 필요",
            file=sys.stderr,
        )
        return 2

    env = detect_environment()
    if not env.ready:
        print(f"{FAIL} apfel 사용 불가:", file=sys.stderr)
        for r in env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    ensure_l0_root_secure()
    ensure_secure_dir(dst_root)

    files = sorted(src_root.rglob("*.jsonl"))
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    if args.resume:
        files = [
            f
            for f in files
            if not (dst_root / f.relative_to(src_root)).exists()
        ]
        print(f"--resume: 기존 결과 skip, {len(files)} 파일 남음")

    if not files:
        print("처리할 파일 없음 (이미 모두 백필됨)")
        return 0

    print(f"백필 시작: {len(files)} 파일 → {dst_root}")
    if args.limit:
        print(f"  --limit {args.limit} 적용")

    total_counts: dict[str, int] = {}
    failed: list[tuple[Path, str]] = []
    started = time.monotonic()

    for i, src_file in enumerate(files, 1):
        rel = src_file.relative_to(src_root)
        size_kb = src_file.stat().st_size / 1024
        print(
            f"[{i}/{len(files)}] {rel} ({size_kb:.0f} KB) ",
            end="",
            flush=True,
        )

        # 청크별 진행 표시 — dot 출력 (10청크마다 카운터)
        chunk_state = {"shown": 0}

        def _on_chunk(
            current: int,
            total: int,
            *,
            state: dict[str, int] = chunk_state,
        ) -> None:
            print(".", end="", flush=True)
            if current % 10 == 0:
                print(f"{current}", end="", flush=True)
            state["shown"] = total

        try:
            text = src_file.read_text(encoding="utf-8", errors="replace")
            if args.max_bytes_per_file > 0:
                text = text[: args.max_bytes_per_file]
            t0 = time.monotonic()
            result = redact_full(text, env=env, on_chunk=_on_chunk)
            elapsed = time.monotonic() - t0

            dst_file = dst_root / rel
            ensure_secure_dir(dst_file.parent)
            dst_file.write_text(result.redacted, encoding="utf-8")
            with contextlib.suppress(OSError):
                os.chmod(dst_file, L0_FILE_MODE)

            for cat, n in result.category_counts().items():
                total_counts[cat] = total_counts.get(cat, 0) + n

            print(
                f" → {chunk_state['shown']}청크, "
                f"{len(result.detections)}건, {elapsed:.1f}s"
            )
        except Exception as exc:
            failed.append((src_file, str(exc)))
            print(f" → 실패: {exc}", file=sys.stderr)

    total_elapsed = time.monotonic() - started

    print("=" * 50)
    print(f"총 시간: {total_elapsed:.1f}s ({total_elapsed/60:.1f}분)")
    print("카테고리별 검출 합계:")
    if not total_counts:
        print("  (검출 0)")
    for cat, n in sorted(total_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")
    print(f"실패 파일: {len(failed)}")
    return 1 if failed else 0


def cmd_collect_obsidian(args: argparse.Namespace) -> int:
    """Obsidian vault → L0 mirror (incremental)."""
    vault: Path = args.vault.expanduser().resolve()
    dst_root: Path = args.dst.expanduser().resolve()

    if not vault.is_dir():
        print(f"{FAIL} vault 없음: {vault}", file=sys.stderr)
        print(
            "  --vault PATH로 지정하거나 SYNAPSE_OBSIDIAN_VAULT 환경변수 설정",
            file=sys.stderr,
        )
        return 2

    print(f"수집 시작: {vault} → {dst_root}")
    stats = collect_obsidian(vault_path=vault, dst_root=dst_root)
    print(stats.summary())

    if stats.errors:
        print("에러:", file=sys.stderr)
        for path, msg in stats.errors:
            print(f"  {path}: {msg}", file=sys.stderr)
        return 1
    return 0


def cmd_collect_claude_code(args: argparse.Namespace) -> int:
    """Claude Code 로그를 L0로 mirror (incremental)."""
    claude_home: Path = args.src.expanduser().resolve()
    dst_root: Path = args.dst.expanduser().resolve()

    if not claude_home.is_dir():
        print(f"{FAIL} Claude home 없음: {claude_home}", file=sys.stderr)
        return 2

    print(f"수집 시작: {claude_home} → {dst_root}")
    stats = collect_claude_code(claude_home=claude_home, dst_root=dst_root)
    print(stats.summary())

    if stats.errors:
        print("에러:", file=sys.stderr)
        for path, msg in stats.errors:
            print(f"  {path}: {msg}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synapse-memory",
        description="Personal knowledge memory & RAG layer.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    p_doctor = sub.add_parser("doctor", help="환경 진단 (apfel/macOS/Apple Silicon)")
    p_doctor.set_defaults(func=cmd_doctor)

    p_collect = sub.add_parser("collect", help="외부 데이터 수집")
    collect_sub = p_collect.add_subparsers(dest="source", required=True, metavar="SOURCE")

    p_cc = collect_sub.add_parser(
        "claude-code", help="Claude Code 로그를 L0로 mirror"
    )
    p_cc.add_argument(
        "--src",
        type=Path,
        default=DEFAULT_CLAUDE_HOME,
        help=f"Claude home (기본: {DEFAULT_CLAUDE_HOME})",
    )
    p_cc.add_argument(
        "--dst",
        type=Path,
        default=l0_root() / "raw" / "claude-code",
        help="L0 mirror 루트 (기본: ~/.synapse/private/raw/claude-code)",
    )
    p_cc.set_defaults(func=cmd_collect_claude_code)

    p_obs = collect_sub.add_parser(
        "obsidian", help="Obsidian vault를 L0로 mirror"
    )
    p_obs.add_argument(
        "--vault",
        type=Path,
        default=get_vault_path(),
        help=f"Vault 경로 (기본: {get_vault_path()})",
    )
    p_obs.add_argument(
        "--dst",
        type=Path,
        default=l0_root() / "raw" / "obsidian",
        help="L0 mirror 루트 (기본: ~/.synapse/private/raw/obsidian)",
    )
    p_obs.set_defaults(func=cmd_collect_obsidian)

    p_redact = sub.add_parser("redact", help="Pass 1+2 redaction 도구")
    redact_sub = p_redact.add_subparsers(
        dest="action", required=True, metavar="ACTION"
    )
    p_backfill = redact_sub.add_parser(
        "backfill", help="L0 raw 전체에 redaction 적용"
    )
    backfill_sub = p_backfill.add_subparsers(
        dest="source", required=True, metavar="SOURCE"
    )
    p_bf_cc = backfill_sub.add_parser(
        "claude-code", help="Claude Code raw 백필"
    )
    p_bf_cc.add_argument(
        "--limit",
        type=int,
        default=0,
        help="처리할 파일 수 제한 (0=무제한, 점진 테스트용)",
    )
    p_bf_cc.add_argument(
        "--max-bytes-per-file",
        type=int,
        default=0,
        help="파일당 처리 최대 바이트 (0=전체). 분포 측정 샘플링용.",
    )
    p_bf_cc.add_argument(
        "--resume",
        action="store_true",
        help="이미 백필된 파일 skip",
    )
    p_bf_cc.set_defaults(func=cmd_redact_backfill_claude_code)

    p_eval = sub.add_parser("eval", help="평가/측정")
    eval_sub = p_eval.add_subparsers(dest="kind", required=True, metavar="KIND")
    p_golden = eval_sub.add_parser(
        "golden", help="골든셋 정확도 측정 (P/R/F1)"
    )
    p_golden.add_argument(
        "--set",
        type=Path,
        default=None,
        help=f"골든셋 JSON 파일 (기본: {default_synthetic_path()})",
    )
    p_golden.add_argument(
        "--show-failures",
        type=int,
        default=10,
        help="실패 sample을 N개까지 출력 (0=숨김)",
    )
    p_golden.set_defaults(func=cmd_eval_golden)

    p_card = sub.add_parser("card", help="Project/Company Card 관리")
    card_sub = p_card.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_card_list = card_sub.add_parser("list", help="Card 목록")
    p_card_list.add_argument(
        "--type",
        choices=["project", "company", "all"],
        default="all",
    )
    p_card_list.set_defaults(func=cmd_card_list)

    p_card_show = card_sub.add_parser("show", help="Card 내용")
    p_card_show.add_argument("card_id", help="card 파일명 (확장자 제외)")
    p_card_show.add_argument(
        "--type", choices=["project", "company"], default="project"
    )
    p_card_show.set_defaults(func=cmd_card_show)

    p_card_new = card_sub.add_parser("new", help="Card 빈 템플릿 생성")
    p_card_new.add_argument("card_id", help="slug. 파일명이 됨")
    p_card_new.add_argument("display_name", help="사람 읽는 이름")
    p_card_new.add_argument(
        "--type", choices=["project", "company"], default="project"
    )
    p_card_new.add_argument(
        "--force", action="store_true", help="기존 파일 덮어쓰기"
    )
    p_card_new.set_defaults(func=cmd_card_new)

    p_card_gen = card_sub.add_parser(
        "generate", help="classify된 cluster들로 Card 자동 생성 (Claude)"
    )
    p_card_gen.add_argument(
        "--kind",
        choices=["project", "company", "all"],
        default="all",
    )
    p_card_gen.add_argument(
        "--limit", type=int, default=0, help="처리할 cluster 수 (0=전체)"
    )
    p_card_gen.add_argument(
        "--model",
        default="sonnet",
        help="AI 모델 (sonnet 권장 — yaml 형식 안정적)",
    )
    p_card_gen.add_argument(
        "--force", action="store_true", help="기존 Card 덮어쓰기"
    )
    p_card_gen.set_defaults(func=cmd_card_generate)

    p_cluster = sub.add_parser(
        "cluster", help="raw에서 같은 프로젝트로 묶기"
    )
    cluster_sub = p_cluster.add_subparsers(
        dest="action", required=True, metavar="ACTION"
    )
    p_cl_scan = cluster_sub.add_parser("scan", help="모든 raw 스캔 + 클러스터 출력")
    p_cl_scan.add_argument(
        "--show-details",
        type=int,
        default=5,
        help="상위 N개 클러스터 상세 출력 (0=요약만)",
    )
    p_cl_scan.set_defaults(func=cmd_cluster_scan)

    p_cl_class = cluster_sub.add_parser(
        "classify", help="cluster를 Claude로 카테고리 분류"
    )
    p_cl_class.add_argument(
        "--limit", type=int, default=0, help="처리할 cluster 수 (0=전체)"
    )
    p_cl_class.add_argument(
        "--resume", action="store_true", help="이미 분류된 cluster skip"
    )
    p_cl_class.add_argument(
        "--model",
        default="haiku",
        help="AI 모델 (haiku/sonnet/opus). 기본 haiku — 단순 분류에 충분",
    )
    p_cl_class.set_defaults(func=cmd_cluster_classify)

    p_rag = sub.add_parser("rag", help="벡터 검색 (RAG)")
    rag_sub = p_rag.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_rag_idx = rag_sub.add_parser("index", help="Card → 벡터 DB 인덱싱")
    p_rag_idx.add_argument(
        "--rebuild", action="store_true", help="기존 collection 비우고 처음부터"
    )
    p_rag_idx.set_defaults(func=cmd_rag_index)

    p_rag_search = rag_sub.add_parser("search", help="자연어 query → top-k Card")
    p_rag_search.add_argument("query", help="검색 자연어")
    p_rag_search.add_argument("--top-k", type=int, default=5)
    p_rag_search.add_argument(
        "--show-snippet", action="store_true", help="결과 본문 일부 출력"
    )
    p_rag_search.set_defaults(func=cmd_rag_search)

    p_ask = sub.add_parser(
        "ask", help="자연어 질의 → RAG retrieve → AI 답변"
    )
    p_ask.add_argument("query", help="자연어 질문")
    p_ask.add_argument("--top-k", type=int, default=5)
    p_ask.add_argument("--model", default="sonnet")
    p_ask.add_argument(
        "--kind",
        choices=["project", "company"],
        help="특정 Card 종류만 retrieve",
    )
    p_ask.set_defaults(func=cmd_ask)

    p_feedback = sub.add_parser("feedback", help="답변/Card/Pattern 피드백 기록")
    feedback_sub = p_feedback.add_subparsers(
        dest="feedback_target", required=True, metavar="TARGET"
    )

    def add_feedback_action_args(p: argparse.ArgumentParser) -> None:
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--accept", action="store_true", help="긍정 피드백")
        group.add_argument("--reject", help="부정 피드백 이유")
        group.add_argument("--weight", type=float, help="직접 가중치 delta (-1.0~1.0)")
        p.add_argument("--vault-path", help="vault 경로 override")
        p.set_defaults(func=cmd_feedback)

    p_fb_last = feedback_sub.add_parser("last", help="직전 답변에 피드백")
    p_fb_last.set_defaults(target_ref=None)
    add_feedback_action_args(p_fb_last)

    p_fb_card = feedback_sub.add_parser("card", help="특정 Card에 피드백")
    p_fb_card.add_argument("target_ref", help="card id")
    add_feedback_action_args(p_fb_card)

    p_fb_pattern = feedback_sub.add_parser("pattern", help="특정 DecisionPattern에 피드백")
    p_fb_pattern.add_argument("target_ref", help="pattern id")
    add_feedback_action_args(p_fb_pattern)

    p_cost = sub.add_parser("cost", help="비용/토큰 관측")
    cost_sub = p_cost.add_subparsers(dest="action", required=True, metavar="ACTION")
    p_cost_summary = cost_sub.add_parser("summary", help="최근 비용 요약")
    p_cost_summary.add_argument("--days", type=int, default=30)
    p_cost_summary.add_argument("--by", choices=("command", "model"), default="command")
    p_cost_summary.add_argument("--json", action="store_true", help="JSON 출력")
    p_cost_summary.set_defaults(func=cmd_cost_summary)

    p_me = sub.add_parser("me", help="클론 모드 endpoints")
    me_sub = p_me.add_subparsers(dest="action", required=True, metavar="ACTION")
    p_resume = me_sub.add_parser(
        "draft-resume", help="회사 맞춤 이력서 자동 작성"
    )
    p_resume.add_argument(
        "company_id",
        help="CompanyCard 파일명 슬러그 (예: danggeun, 메가스터디)",
    )
    p_resume.add_argument("--top-k", type=int, default=6)
    p_resume.add_argument("--model", default="sonnet")
    p_resume.set_defaults(func=cmd_me_draft_resume)

    p_up = me_sub.add_parser(
        "update-profile",
        help="raw → ProfileFact/DecisionPattern 후보 → MemoryInbox PR",
    )
    p_up.add_argument(
        "--sample-lines",
        type=int,
        default=200,
        help="history.jsonl 마지막 N줄 분석",
    )
    p_up.add_argument("--model", default="sonnet")
    p_up.add_argument(
        "--facts-only",
        action="store_true",
        help="DecisionPattern 추출 skip (비용 절감)",
    )
    p_up.set_defaults(func=cmd_me_update_profile)

    p_wdt = me_sub.add_parser(
        "what-did-i-think", help="주제에 대한 과거 사고 회상"
    )
    p_wdt.add_argument("topic", help="회상할 주제")
    p_wdt.add_argument("--top-k", type=int, default=8)
    p_wdt.add_argument("--model", default="sonnet")
    p_wdt.add_argument(
        "--timeline",
        action="store_true",
        help="시간순(period_end desc) + 분기 그룹 출력 (FR-A1)",
    )
    p_wdt.add_argument(
        "--by",
        choices=("time", "distance"),
        default=None,
        help="정렬 모드: time (= --timeline) 또는 distance (기본)",
    )
    p_wdt.add_argument(
        "--limit",
        type=int,
        default=20,
        help="--timeline 모드 출력 카드 최대 수 (1~100, 기본 20)",
    )
    p_wdt.set_defaults(func=cmd_me_what_did_i_think)

    p_dec = me_sub.add_parser(
        "decide", help="의사결정 코파일럿 (Profile + Patterns + RAG)"
    )
    p_dec.add_argument("situation", help="결정할 상황")
    p_dec.add_argument("--top-k", type=int, default=6)
    p_dec.add_argument("--model", default="sonnet")
    p_dec.set_defaults(func=cmd_me_decide)

    p_gen = me_sub.add_parser(
        "generate",
        help="recipe 기반 결과물 생성 (007-me-recipes: weekly_report / journal / ...)",
    )
    p_gen.add_argument("recipe", help="recipe 이름 (me recipes list 로 확인 — 추후)")
    p_gen.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="recipe input_schema 의 key=value (여러 번 지정 가능)",
    )
    p_gen.add_argument("--language", default=None, help="locale precedence 0 순위")
    p_gen.add_argument("--domain", default=None, help="domain precedence 0 순위")
    p_gen.add_argument("--model", default=None, help="recipe 의 model 기본값 override")
    p_gen.add_argument("--vault", default=None, help="vault 경로 override")
    p_gen.add_argument(
        "--today",
        default=None,
        help="YYYY-MM-DD — {today} placeholder + 파일명 날짜 override (테스트용)",
    )
    p_gen.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM 호출·저장·last_answer 생략. system/user prompt 미리보기만",
    )
    p_gen.set_defaults(func=cmd_me_generate)

    p_daily = sub.add_parser("daily", help="일일 통합 파이프라인 (5분 워크플로)")
    p_daily.add_argument(
        "--only",
        help=f"이 단계들만 (comma-separated). 가능: {','.join(STEPS)}",
    )
    p_daily.add_argument("--skip", help="제외할 단계 (comma-separated)")
    p_daily.add_argument("--classify-model", default="haiku")
    p_daily.add_argument("--generate-model", default="sonnet")
    p_daily.add_argument("--profile-model", default="sonnet")
    p_daily.add_argument("--profile-sample-lines", type=int, default=200)
    p_daily.add_argument("--profile-facts-only", action="store_true")
    p_daily.add_argument("--dry-run", action="store_true", help="실행 안 하고 단계만")
    p_daily.set_defaults(func=cmd_daily)

    p_rl = sub.add_parser(
        "redactlist", help="NDA 회사/프로젝트 강제 마스킹 리스트 관리"
    )
    rl_sub = p_rl.add_subparsers(dest="action", required=True, metavar="ACTION")
    p_rl_show = rl_sub.add_parser("show", help="현재 항목 출력")
    p_rl_show.set_defaults(func=cmd_redactlist_show)
    p_rl_add = rl_sub.add_parser("add", help="항목 추가")
    p_rl_add.add_argument("item", help="회사명/프로젝트명/키워드")
    p_rl_add.set_defaults(func=cmd_redactlist_add)
    p_rl_rm = rl_sub.add_parser("remove", help="항목 제거")
    p_rl_rm.add_argument("item", help="제거할 항목 (정확히 일치)")
    p_rl_rm.set_defaults(func=cmd_redactlist_remove)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    with command_context(_command_name(args)):
        return int(args.func(args))


def _command_name(args: argparse.Namespace) -> str:
    cmd = str(getattr(args, "cmd", "unknown") or "unknown")
    parts = [cmd]
    for attr in ("source", "kind", "action", "feedback_target"):
        value = getattr(args, attr, None)
        if isinstance(value, str) and value:
            parts.append(value.replace("-", "_"))
    return ".".join(parts)


if __name__ == "__main__":
    sys.exit(main())
