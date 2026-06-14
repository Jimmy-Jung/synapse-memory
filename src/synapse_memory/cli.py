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

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import sys


def _fast_path_hook() -> None:
    """`synapse-memory hook run ...`은 무거운 CLI import 전에 처리한다."""
    if len(sys.argv) >= 3 and sys.argv[1] == "hook" and sys.argv[2] == "run":
        from synapse_memory.hooks.session_start import main as hook_main

        raise SystemExit(hook_main())


_fast_path_hook()

import argparse  # noqa: E402
import contextlib  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Iterable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from synapse_memory import __version__  # noqa: E402
from synapse_memory.cards import (  # noqa: E402
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
from synapse_memory.cards.auto_classify import (  # noqa: E402
    classify_cluster,
    load_classifications,
    save_classifications,
)
from synapse_memory.cards.auto_generate import (  # noqa: E402
    generate_company_card,
    generate_project_card,
)
from synapse_memory.cards.company import companies_dir  # noqa: E402
from synapse_memory.cards.project import projects_dir  # noqa: E402
from synapse_memory.clusters import identify_clusters  # noqa: E402
from synapse_memory.collectors.claude_code import (  # noqa: E402
    DEFAULT_CLAUDE_HOME,
    collect_claude_code,
)
from synapse_memory.collectors.obsidian import (  # noqa: E402
    collect_obsidian,
    get_vault_path,
)
from synapse_memory.collectors.obsidian import get_vault_path as get_obsidian_vault  # noqa: E402
from synapse_memory.cost.events import command_context  # noqa: E402
from synapse_memory.cost.summary import (  # noqa: E402
    load_summary,
    render_summary_json,
    render_summary_table,
)
from synapse_memory.daily import STEPS, StageStatus, run_daily  # noqa: E402
from synapse_memory.doctor import (  # noqa: E402
    DiagnosticStatus,
    apply_fix_actions,
    apply_set_config_vault,
    diagnose_private_permissions,
    diagnose_runtime_shim,
    diagnose_vault_config_consistency,
    planned_fix_actions,
)
from synapse_memory.endpoints.ask import ask  # noqa: E402
from synapse_memory.endpoints.persona import (  # noqa: E402
    decide,
    draft_resume,
    what_did_i_think,
)
from synapse_memory.eval.golden import (  # noqa: E402
    default_synthetic_path,
    evaluate,
    load_golden_set,
)
from synapse_memory.feedback.events import (  # noqa: E402
    FeedbackAction,
    append_feedback_event,
    build_feedback_event,
)
from synapse_memory.feedback.targets import (  # noqa: E402
    FeedbackTarget,
    resolve_card_target,
    resolve_last_answer_targets,
    resolve_pattern_target,
)
from synapse_memory.llm import AIError, detect_ai_environment  # noqa: E402
from synapse_memory.llm.apfel import MIN_MACOS_MAJOR, detect_environment  # noqa: E402
from synapse_memory.profile.extract import (  # noqa: E402
    extract_decision_patterns,
    extract_profile_facts,
    save_profile_update,
)
from synapse_memory.profile.ingest import (  # noqa: E402
    SUPPORTED_EXTENSIONS,
    ingest_files,
)
from synapse_memory.rag import (  # noqa: E402
    embed_query,
    index_cards,
    open_vector_store,
)
from synapse_memory.rag.bm25 import BM25IndexError  # noqa: E402
from synapse_memory.rag.embeddings import (  # noqa: E402
    EmbeddingError,
    EmbeddingUnavailableError,
)
from synapse_memory.rag.vector_store import VectorStoreError  # noqa: E402
from synapse_memory.redaction import redact_full  # noqa: E402
from synapse_memory.redaction.redactlist import (  # noqa: E402
    add_redactlist_item,
    load_redactlist,
    remove_redactlist_item,
)
from synapse_memory.status import DailyAlreadyRunningError  # noqa: E402
from synapse_memory.storage.l0 import (  # noqa: E402
    L0_DIR_MODE,
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)
from synapse_memory.storage.last_response import load_last_answer  # noqa: E402
from synapse_memory.wiki.index import index_wiki_pages  # noqa: E402
from synapse_memory.wiki.ingest import ingest_source  # noqa: E402
from synapse_memory.wiki.query import ask_wiki  # noqa: E402

OK = "✓"
FAIL = "✗"

# 대화형 endpoint(ask / me *) 가 사람-터미널에서 직접 호출되었을 때 안내하는 경고.
# Claude Code / Codex 의 slash 명령이 subprocess 로 호출하면 SYNAPSE_FROM_AGENT=1 환경변수가
# 설정되어 있어 경고가 생략됩니다. stdout 이 pipe 인 경우(자동화)도 통과.
_INTERACTIVE_GUARD_DELAY_SECONDS = 3
_INTERACTIVE_GUARD_MESSAGE = (
    "⚠  {command} 는 LLM 대화 컨텍스트에서 호출할 때 가장 자연스럽게 동작합니다.\n"
    "   Claude Code / Codex 안에서 `/sm:{slash}` 슬래시 명령으로 호출하면\n"
    "   결과가 대화에 인라인되고 후속 질문에 컨텍스트가 유지됩니다.\n"
    "   계속 진행하려면 {delay}초 기다리세요. 즉시 우회: SYNAPSE_FROM_AGENT=1\n"
)


def _stdout_is_tty() -> bool:
    """sys.stdout.isatty() 의 thin wrapper — 테스트에서 monkeypatch 하기 위함."""
    return sys.stdout.isatty()


def _interactive_guard(command: str, slash: str) -> None:
    """대화형 endpoint 에서 사람의 직접 CLI 호출을 부드럽게 만류한다.

    config의 ``interactive_guard.enabled = false``이면 안내 자체를 생략.
    대기 시간은 ``interactive_guard.delay_seconds`` 사용.
    """
    if os.environ.get("SYNAPSE_FROM_AGENT"):
        return
    if not _stdout_is_tty():
        return
    try:
        from synapse_memory.config import get_config

        cfg = get_config()
        if not cfg.interactive_guard.enabled:
            return
        delay = cfg.interactive_guard.delay_seconds
    except Exception:
        delay = _INTERACTIVE_GUARD_DELAY_SECONDS
    sys.stderr.write(
        _INTERACTIVE_GUARD_MESSAGE.format(command=command, slash=slash, delay=delay)
    )
    sys.stderr.flush()
    time.sleep(delay)


def _arg_or_config(arg_value: Any, cfg_path: str, fallback: Any = None) -> Any:
    """CLI 인자가 None이면 config 값으로 폴백.

    우선순위: CLI 인자 > ``~/.synapse/config.yaml`` > fallback 인자 > None.

    Args:
        arg_value: argparse가 채운 값. None이면 config 조회.
        cfg_path: 점 표기 키 경로 (예: ``top_k.ask``).
        fallback: config 조회 실패 시 사용할 최종 default.
    """
    if arg_value is not None:
        return arg_value
    try:
        from synapse_memory.config import get_config, get_value

        return get_value(get_config(), cfg_path)
    except (KeyError, Exception):
        return fallback


def _enforce_cost_cap(command: str) -> None:
    """ask/me 계열 호출 직전 월 cap 검사. lazy import."""
    try:
        from synapse_memory.cost.cap import enforce_cost_cap

        enforce_cost_cap(command)
    except SystemExit:
        raise
    except Exception:
        # cap 시스템 자체가 실패해도 호출은 진행 (best-effort)
        pass


def _resolve_model(arg_model: str | None, task: str) -> str | None:
    """task별 model 폴백 — provider 인식.

    1) CLI 인자 명시 → 그대로
    2) ``SYNAPSE_AI_PROVIDER`` env → 그 provider의 task model
    3) Codex/Claude 런타임 감지 → 실제 호출 provider의 task model
    4) config ``ai_provider`` → 그 provider의 task model
    5) provider가 ``auto``이거나 결정 불가 → None (detect_ai_environment가 자체 결정)

    Args:
        arg_model: argparse가 채운 값. None이면 config 폴백.
        task: ``models.<provider>.<task>``의 task 이름 (예: ``ask``, ``classify``).
    """
    if arg_model is not None:
        return arg_model
    try:
        from synapse_memory.config import get_config

        provider = (
            os.environ.get("SYNAPSE_AI_PROVIDER")
            or _runtime_ai_provider()
            or get_config().ai_provider
        )
        if provider == "auto":
            return None
        cfg = get_config()
        provider_models = getattr(cfg.models, provider, None)
        if provider_models is None:
            return None
        return getattr(provider_models, task, None)
    except Exception:
        return None


def _runtime_ai_provider() -> str | None:
    if any(
        os.environ.get(name)
        for name in (
            "CODEX_CI",
            "CODEX_THREAD_ID",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        )
    ):
        return "codex"
    if any(
        os.environ.get(name)
        for name in (
            "CLAUDECODE",
            "CLAUDE_CODE",
            "CLAUDE_PROJECT_DIR",
        )
    ):
        return "claude"
    return None


def run_doctor_fix(*, assume_yes: bool = False) -> int:
    """Whitelisted repair flow for non-developer onboarding drift."""
    private_root = l0_root()
    shim_path = Path.home() / ".synapse" / "bin" / "synapse-memory"
    diagnostics = [
        diagnose_private_permissions(private_root),
        diagnose_runtime_shim(shim_path),
    ]
    actions = planned_fix_actions(diagnostics)

    if not actions:
        print("자동 복구할 항목 없음")
        return 0 if all(result.status == "ok" for result in diagnostics) else 1

    print("Planned fixes:")
    for index, action in enumerate(actions, start=1):
        print(f"{index}. {action.id} - {action.description} (risk={action.risk})")

    if not assume_yes:
        print("Applying in 0.5s. Press Ctrl+C to cancel.")
        time.sleep(0.5)

    applied = apply_fix_actions(actions)
    failed = 0
    for result in applied:
        print(f"{result.action_id}: {result.status} - {result.summary}")
        if result.status != "success":
            failed += 1
    return 1 if failed else 0


def run_doctor_fix_config(*, assume_yes: bool = False) -> int:
    """config.yaml vault 갱신 — silent overwrite 차단을 위해 별도 명시 flag.

    diagnose_vault_config_consistency 가 fixable=True 인 경우에만 동작.
    --yes 없으면 stdin 동의 필요.
    """
    from synapse_memory.config import load_config

    cfg = load_config()
    result = diagnose_vault_config_consistency(cfg.vault)

    if result.status == DiagnosticStatus.OK:
        print(f"{OK} {result.message}")
        return 0

    if not result.fixable or result.target is None:
        print(f"{FAIL} {result.message}")
        return 1

    print("config.yaml vault 갱신 후보:")
    print(f"  현재 config: {cfg.vault!r}")
    print(f"  감지된 vault: {result.target}")
    print(f"  사유: {result.message}")

    if not assume_yes:
        try:
            answer = input("이 경로로 갱신할까요? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("취소됨. config 변경 없음.")
            return 0

    fix_result = apply_set_config_vault(result.target)
    print(f"{OK} {fix_result.summary}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """환경 진단 — apfel/macOS/Apple Silicon."""
    if getattr(args, "fix_config", False):
        return run_doctor_fix_config(assume_yes=bool(getattr(args, "yes", False)))
    if getattr(args, "fix", False):
        return run_doctor_fix(assume_yes=bool(getattr(args, "yes", False)))

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

    # vault config 일관성 — config.yaml vault vs 실제 detection
    try:
        from synapse_memory.config import load_config

        vc_cfg = load_config()
        vc_result = diagnose_vault_config_consistency(vc_cfg.vault)
        if vc_result.status == DiagnosticStatus.OK:
            print(f"{OK} {vc_result.message}")
        elif vc_result.status == DiagnosticStatus.WARN:
            print(f"⚠ {vc_result.message}")
        else:
            print(f"{FAIL} {vc_result.message}")
    except Exception as exc:
        print(f"⚠ vault config 진단 실패: {exc}")

    # vault `90_System/Private/` deny 일관성 — 외부 AI 차단 점검
    try:
        from synapse_memory.config import load_config
        from synapse_memory.doctor import diagnose_private_folder_deny

        pf_cfg = load_config()
        if pf_cfg.vault is None:
            raise ValueError("config.yaml vault 미설정")
        pf_result = diagnose_private_folder_deny(pf_cfg.vault)
        if pf_result.status == DiagnosticStatus.OK:
            print(f"{OK} {pf_result.message}")
        elif pf_result.status == DiagnosticStatus.WARN:
            print(f"⚠ {pf_result.message}")
        else:
            print(f"{FAIL} {pf_result.message}")
    except Exception as exc:
        print(f"⚠ Private 폴더 deny 진단 실패: {exc}")

    # Dataview 플러그인 점검 — MOC 동적 인덱스 의존성
    try:
        from synapse_memory.config import load_config
        from synapse_memory.doctor import diagnose_dataview_plugin

        dv_cfg = load_config()
        if dv_cfg.vault is None:
            raise ValueError("config.yaml vault 미설정")
        dv_result = diagnose_dataview_plugin(dv_cfg.vault)
        if dv_result.status == DiagnosticStatus.OK:
            print(f"{OK} {dv_result.message}")
        elif dv_result.status == DiagnosticStatus.WARN:
            print(f"⚠ {dv_result.message}")
        else:
            print(f"{FAIL} {dv_result.message}")
    except Exception as exc:
        print(f"⚠ Dataview 플러그인 진단 실패: {exc}")

    # Claude Code/Codex SessionStart hook 설치 상태
    try:
        from synapse_memory.hooks.install import diagnose_session_hook

        hook_result = diagnose_session_hook()
        if hook_result.installed:
            print(f"{OK} {hook_result.message}")
        else:
            print(f"⚠ {hook_result.message}")
            print("  설치: synapse-memory hook install")
    except Exception as exc:
        print(f"⚠ SessionStart hook 진단 실패: {exc}")

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
            for project_card in cards:
                period = project_card.period_start or ""
                if project_card.period_end:
                    period = f"{period} ~ {project_card.period_end}"
                print(
                    f"{project_card.project_id:<25} {project_card.status:<12} "
                    f"{(project_card.role or '')[:24]:<25} {period:<20}"
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
            for company_card in cards_c:
                print(
                    f"{company_card.company_id:<25} {company_card.status:<14} "
                    f"{(company_card.country or ''):<8} {len(company_card.positions):<5}"
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
            company_card = load_company_card(cid)
            print(serialize_company_card(company_card))
        else:
            project_card = load_project_card(cid)
            print(serialize_project_card(project_card))
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
    include_raw = bool(getattr(args, "include_raw", False))
    print(f"인덱싱 시작 (rebuild={args.rebuild}, include_raw={include_raw})")
    try:
        store = open_vector_store()

        def _progress(stage: str, current: int, total: int) -> None:
            if current == 1:
                print(f"  [{stage}] {total}개 임베딩 중...")

        stats = index_cards(
            store=store,
            rebuild=args.rebuild,
            include_raw=include_raw,
            on_progress=_progress,
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
        f"insight={getattr(stats, 'insight_cards', 0)} "
        f"raw_obsidian={getattr(stats, 'raw_obsidian_chunks', 0)} "
        f"raw_claude_code={getattr(stats, 'raw_claude_code_chunks', 0)} "
        f"bm25={getattr(stats, 'bm25_documents', 0)} "
        f"bytes={stats.bytes_indexed}"
    )
    print(f"총 벡터: {open_vector_store().count()}")
    if stats.failed:
        for stage, msg in stats.failed:
            print(f"  실패: {stage} — {msg}", file=sys.stderr)
        return 1
    return 0


def cmd_me_what_did_i_think(args: argparse.Namespace) -> int:
    args.top_k = _arg_or_config(args.top_k, "top_k.recall", 8)
    args.model = _resolve_model(args.model, "recall")
    _enforce_cost_cap("persona what-did-i-think")
    _interactive_guard("persona what-did-i-think", "recall")

    # FR-009 — --timeline + --by distance 충돌 검증
    timeline_flag = bool(getattr(args, "timeline", False))
    hybrid_flag = bool(getattr(args, "hybrid", False))
    by_arg = getattr(args, "by", None)
    if hybrid_flag and (timeline_flag or by_arg == "time"):
        print(
            "error: --timeline and --hybrid conflict — pick one.",
            file=sys.stderr,
        )
        return 1
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
            hybrid=hybrid_flag,
        )
    except (
        EmbeddingUnavailableError,
        VectorStoreError,
        BM25IndexError,
        AIError,
        ValueError,
    ) as exc:
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
    args.top_k = _arg_or_config(args.top_k, "top_k.decide", 6)
    args.model = _resolve_model(args.model, "decide")
    _enforce_cost_cap("persona decide")
    _interactive_guard("persona decide", "decide")
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


def cmd_ingest(args: argparse.Namespace) -> int:
    """wiki ingest 엔진 1회 실행."""
    dry = bool(getattr(args, "dry_run", False))
    result = ingest_source(args.source, dry_run=dry, limit=args.limit)
    label = "(dry-run) " if dry else ""
    print(f"{label}ingest {result.source}: docs={result.docs_processed}, "
          f"pages={len(result.pages_written)}")
    if result.pages_written:
        print("  written: " + ", ".join(result.pages_written))
    if result.errors:
        print(f"  errors: {len(result.errors)}")
        for e in result.errors:
            print(f"    - {e}")
    return 1 if result.errors else 0


def cmd_wiki_ask(args: argparse.Namespace) -> int:
    """wiki-first 질의 → 합성 답변 + 인용 (선택적 insight write-back)."""
    res = ask_wiki(args.query, save=getattr(args, "save", False))
    print(res.answer)
    if res.sources:
        print("\n출처: " + ", ".join(f"[[{s}]]" for s in res.sources))
    if res.saved_slug:
        print(f"{OK} insight 저장: {res.saved_slug}")
    return 0


def cmd_wiki_reindex(args: argparse.Namespace) -> int:
    """모든 wiki 페이지를 벡터 스토어에 재인덱싱."""
    count = index_wiki_pages()
    print(f"indexed {count} pages")
    return 0


def cmd_daily(args: argparse.Namespace) -> int:
    """일일 통합 파이프라인."""
    if args.quick:
        print(
            f"⚡ quick mode — 최근 {args.quick_days}일 modified 노트 + "
            f"최대 {args.quick_max_clusters}개 cluster classify. "
            "update_profile auto-skip. full pipeline 은 `synapse-memory daily` (no flag)."
        )

    # CLI 인자가 None이면 config (models.<provider>.<task>) 우선 적용.
    # run_daily는 None을 받으면 자체 기본값 "sonnet"/"haiku"로 폴백.
    classify_model = _resolve_model(args.classify_model, "classify") or "haiku"
    generate_model = _resolve_model(args.generate_model, "card_generate") or "sonnet"
    profile_model = _resolve_model(args.profile_model, "update_profile") or "sonnet"

    try:
        only = _parse_stage_csv(args.only) if args.only else None
        skip = _parse_stage_csv(args.skip) if args.skip else None
        with _daily_status_watcher(
            enabled=bool(args.watch_status and not args.dry_run),
            interval=float(args.status_interval),
        ):
            result = run_daily(
                only=only,
                skip=skip,
                resume_from=args.resume_from,
                classify_model=classify_model,
                generate_model=generate_model,
                profile_model=profile_model,
                profile_sample_lines=args.profile_sample_lines,
                profile_facts_only=args.profile_facts_only,
                quick=args.quick,
                quick_days=args.quick_days,
                quick_max_clusters=args.quick_max_clusters,
                dry_run=args.dry_run,
            )
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except DailyAlreadyRunningError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 3

    if args.dry_run:
        return 0

    print("\n" + "=" * 60)
    print(f"Daily 총 시간: {result.total_elapsed:.1f}s")
    print(
        f"실행 단계: {len(result.steps)}, 실패: {result.errors}, "
        f"경고: {result.warnings}, 건너뜀: {result.skipped}"
    )
    for s in result.steps:
        if s.status == StageStatus.SKIPPED:
            status = "-"
            detail = f"skipped: {s.skip_reason}"
        else:
            status = OK if s.ok else FAIL
            detail = s.summary or s.error
        print(f"  {status} {s.name:<22} {s.elapsed:>6.1f}s  {detail}")
    from synapse_memory.status import STATUS_FILE as _DAILY_STATUS_FILE

    print(f"\n진행률 status: {_DAILY_STATUS_FILE}  ('synapse-memory daily-status'로 조회)")
    return 1 if result.errors else 0


def _parse_stage_csv(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


@contextlib.contextmanager
def _daily_status_watcher(*, enabled: bool, interval: float) -> Iterator[None]:
    if not enabled:
        yield
        return

    from synapse_memory.status import read_status

    stop = threading.Event()
    pid = os.getpid()
    last_signature: tuple[object, ...] | None = None
    poll_interval = max(0.5, interval)

    def watch() -> None:
        nonlocal last_signature
        while not stop.wait(poll_interval):
            status = read_status()
            if status is None or status.pid != pid:
                continue
            signature = (
                status.state,
                status.current_stage,
                status.current_stage_index,
                status.current_item,
                status.current_item_index,
                status.current_item_total,
                tuple(status.completed_stages),
                tuple(status.failed_stages),
            )
            if signature == last_signature:
                continue
            last_signature = signature
            print(_format_daily_status_line(status), flush=True)

    thread = threading.Thread(target=watch, name="daily-status-watch", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)


def _format_daily_status_line(status: Any) -> str:
    if status.current_stage:
        head = (
            f"[daily-status] {status.current_stage} "
            f"({status.current_stage_index}/{status.total_stages})"
        )
    else:
        head = f"[daily-status] {status.state}"
    if status.current_item_total:
        pct = int(status.current_item_index / status.current_item_total * 100)
        head += (
            f" — {status.current_item} "
            f"[{status.current_item_index}/{status.current_item_total}, {pct}%]"
        )
    if status.failed_stages:
        head += f" — failed: {', '.join(status.failed_stages)}"
    return head


def cmd_daily_status(args: argparse.Namespace) -> int:
    """진행 중인/마지막 daily 진행률 조회."""
    from synapse_memory.status import STATUS_FILE, read_status, render_status

    def _print_once() -> int:
        status = read_status()
        if args.json:
            if status is None:
                print("{}")
            else:
                print(status.to_json())
        else:
            print(render_status(status))
        return 0 if status is not None else 1

    if not args.watch:
        return _print_once()

    import time as _time

    interval = max(0.5, float(args.interval))
    last_signature: tuple[str, str, int, str] | None = None
    print(f"watching {STATUS_FILE} (Ctrl-C로 종료, {interval:.1f}s 간격)")
    try:
        while True:
            status = read_status()
            signature: tuple[str, str, int, str] | None = (
                None
                if status is None
                else (
                    status.updated_at,
                    status.current_stage,
                    status.current_item_index,
                    status.state,
                )
            )
            if signature != last_signature:
                print("\n--- " + datetime.datetime.now().isoformat(timespec="seconds"))
                print(render_status(status))
                last_signature = signature
            if status is not None and status.state in {"done", "failed"}:
                return 0 if status.state == "done" else 1
            _time.sleep(interval)
    except KeyboardInterrupt:
        return 130


def cmd_migrate_folders(args: argparse.Namespace) -> int:
    """기존 flat 파일을 {YYYY}/{MM}/ 폴더 구조로 이동."""
    from synapse_memory.collectors.obsidian import get_vault_path
    from synapse_memory.config import get_config
    from synapse_memory.folders.migrate import (
        DAILY_REPORT_PATTERN,
        PROFILE_PATTERN,
        execute_migration,
        scan_flat_files,
    )

    vault = (
        Path(args.vault).expanduser().resolve()
        if args.vault
        else get_vault_path()
    )
    if not vault.is_dir():
        print(f"{FAIL} vault 경로가 존재하지 않습니다: {vault}", file=sys.stderr)
        return 2

    cfg = get_config()
    targets = [
        (vault / cfg.vault_folders.system.ai.memory_inbox, PROFILE_PATTERN, "MemoryInbox"),
        (vault / cfg.vault_folders.system.ai.daily_reports, DAILY_REPORT_PATTERN, "DailyReports"),
    ]

    total_moved = 0
    total_conflicts = 0
    total_skipped: list[Path] = []
    total_errors: list[tuple[Path, str]] = []

    for base, pattern, label in targets:
        plans, skipped = scan_flat_files(base, pattern)
        total_skipped.extend(skipped)
        if not plans and not skipped:
            print(f"  {label:<14} (대상 없음)")
            continue
        result = execute_migration(plans, dry_run=args.dry_run)
        moved_n = len(result.moved)
        conflict_n = len(result.conflicts)
        total_moved += moved_n
        total_conflicts += conflict_n
        total_errors.extend(result.errors)
        prefix = "  dry-run" if args.dry_run else "  이동"
        print(f"{prefix} {label:<14} {moved_n}건, 충돌 {conflict_n}건, skipped {len(skipped)}건")
        for plan in result.moved:
            arrow = "→" if not args.dry_run else "·"
            print(f"    {plan.src.name} {arrow} {plan.dst.relative_to(base)}")
        for src, dst in result.conflicts:
            print(f"    ⚠ 충돌: {src.name} (대상 {dst.relative_to(base)} 이미 존재)", file=sys.stderr)
        for src, err in result.errors:
            print(f"    ✖ 실패: {src.name} — {err}", file=sys.stderr)

    if args.report_unknown and total_skipped:
        print("\n[skipped — 패턴 불일치]")
        for p in total_skipped:
            print(f"  {p}")

    if total_errors:
        return 2
    if total_conflicts:
        return 1
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    """현재 효력 있는 config 출력."""
    from synapse_memory.config import (
        DEFAULT_CONFIG_PATH,
        load_config,
        render_config,
    )

    cfg = load_config()
    if args.json:
        from dataclasses import asdict
        print(json.dumps(asdict(cfg), ensure_ascii=False, indent=2))
        return 0
    print(render_config(cfg, show_advanced=args.advanced))
    if not DEFAULT_CONFIG_PATH.exists():
        print()
        print(f"(파일 없음 — default 값. 변경 시 자동 생성: {DEFAULT_CONFIG_PATH})")
    return 0


def cmd_config_get(args: argparse.Namespace) -> int:
    """단일 키 조회."""
    from synapse_memory.config import get_value, load_config

    cfg = load_config()
    try:
        value = get_value(cfg, args.path)
    except KeyError as e:
        print(f"{FAIL} {e}", file=sys.stderr)
        return 2
    print(value if value is not None else "(미설정)")
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    """단일 키 설정 + 백업 + atomic write."""
    from synapse_memory.config import (
        is_advanced_path,
        is_protected_path,
        load_config,
        save_config,
        set_value,
        validate_config,
    )

    if is_protected_path(args.path):
        print(
            f"{FAIL} 보호된 키 — config로 변경 불가: {args.path}\n"
            "    (보안 핵심 — 코드 PR로만 변경)",
            file=sys.stderr,
        )
        return 3

    cfg = load_config()
    if is_advanced_path(args.path) and not args.force:
        print(
            f"⚠ advanced 키: {args.path}\n"
            "  잘못 변경 시 검색 품질 저하 또는 색인 재생성 필요.\n"
            "  계속하려면 `--force`를 붙이세요.",
            file=sys.stderr,
        )
        return 4

    try:
        set_value(cfg, args.path, args.value)
    except (KeyError, ValueError) as e:
        print(f"{FAIL} {e}", file=sys.stderr)
        return 2

    errors = validate_config(cfg)
    if errors:
        print(f"{FAIL} 검증 실패:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 5

    save_config(cfg)
    print(f"{OK} {args.path} = {args.value}")
    return 0


def cmd_config_edit(_args: argparse.Namespace) -> int:
    """$EDITOR로 config.yaml 직접 편집 (없으면 안내)."""
    from synapse_memory.config import (
        DEFAULT_CONFIG_PATH,
        load_config,
        save_config,
    )

    if not DEFAULT_CONFIG_PATH.exists():
        save_config(load_config(), make_backup=False)
        print(f"{OK} default config 작성: {DEFAULT_CONFIG_PATH}")

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        print(
            "EDITOR 환경변수가 없습니다. 직접 열어 편집하세요:\n"
            f"  {DEFAULT_CONFIG_PATH}",
            file=sys.stderr,
        )
        return 0

    import subprocess

    rc = subprocess.run([editor, str(DEFAULT_CONFIG_PATH)]).returncode
    return rc


def cmd_config_reset(args: argparse.Namespace) -> int:
    """전체 또는 단일 키를 default로 복원."""
    from synapse_memory.config import (
        SynapseConfig,
        get_value,
        load_config,
        save_config,
        set_value,
    )

    if args.path is None:
        save_config(SynapseConfig())
        print(f"{OK} 전체 config를 default로 복원")
        return 0

    default_cfg = SynapseConfig()
    try:
        default_val = get_value(default_cfg, args.path)
    except KeyError as e:
        print(f"{FAIL} {e}", file=sys.stderr)
        return 2

    cfg = load_config()
    try:
        set_value(cfg, args.path, default_val)
    except (KeyError, ValueError) as e:
        print(f"{FAIL} {e}", file=sys.stderr)
        return 2

    save_config(cfg)
    print(f"{OK} {args.path}를 default({default_val})로 복원")
    return 0


def cmd_config_validate(_args: argparse.Namespace) -> int:
    """현재 config 검증 (타입·범위·알려진 키)."""
    from synapse_memory.config import load_config, validate_config

    cfg = load_config()
    errors = validate_config(cfg)
    if not errors:
        print(f"{OK} config 검증 통과")
        return 0
    print(f"{FAIL} 검증 실패 ({len(errors)}건):", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


def cmd_assistant_status(args: argparse.Namespace) -> int:
    """비서 모드용 read-only 진단 묶음 (vault·doctor·inbox·draft·last-daily)."""
    from synapse_memory.assistant_status import gather_status, render_status

    status = gather_status()
    if args.json:
        print(status.to_json())
    else:
        print(render_status(status))
    return 0


def _resolve_vault_or_fail() -> Path:
    """env 또는 인자에서 vault 경로 해결. 없으면 종료."""
    from synapse_memory.assistant_status import resolve_vault_path

    v = resolve_vault_path()
    if v is None or not v.exists():
        print(
            f"{FAIL} vault 경로 없음 — `export SYNAPSE_OBSIDIAN_VAULT='<vault 경로>'`",
            file=sys.stderr,
        )
        sys.exit(2)
    return v


def cmd_cleanup_scan(args: argparse.Namespace) -> int:
    """vault read-only 스캔 — 청소 후보 출력 (이동 없음)."""
    from synapse_memory.cleanup import scan_cleanup_candidates

    vault = _resolve_vault_or_fail()
    plan = scan_cleanup_candidates(
        vault,
        inbox_stale_days=args.inbox_days,
        dormant_project_days=args.dormant_days,
        old_resume_days=args.resume_days,
        stale_memory_inbox_days=args.memory_inbox_days,
        old_daily_reports_days=args.report_days,
    )
    if args.json:
        print(plan.to_json())
        return 0

    by_kind = plan.by_kind()
    if not plan.candidates:
        print("정리 후보 없음 — vault가 깨끗합니다.")
        return 0
    print(f"vault: {plan.vault_path}")
    print(f"scanned_at: {plan.scanned_at}")
    print(f"총 후보: {len(plan.candidates)}건")
    print()
    for kind, items in by_kind.items():
        print(f"[{kind}] {len(items)}건")
        for c in items[:5]:
            age_part = f" ({c.age_days}일)" if c.age_days is not None else ""
            print(f"  - {c.source_path}{age_part} — {c.reason}")
        if len(items) > 5:
            print(f"  ... 외 {len(items) - 5}건")
        print()
    print(
        "실제 이동하려면: `synapse-memory cleanup apply --apply "
        "[--category <kind1,kind2>]`"
    )
    return 0


def cmd_cleanup_apply(args: argparse.Namespace) -> int:
    """선택된 청소 후보를 archive 폴더로 이동 + 매니페스트 작성."""
    from synapse_memory.cleanup import (
        apply_cleanup,
        scan_cleanup_candidates,
        write_cleanup_manifest,
    )

    vault = _resolve_vault_or_fail()
    plan = scan_cleanup_candidates(
        vault,
        inbox_stale_days=args.inbox_days,
        dormant_project_days=args.dormant_days,
        old_resume_days=args.resume_days,
        stale_memory_inbox_days=args.memory_inbox_days,
        old_daily_reports_days=args.report_days,
    )

    selected = plan.candidates
    if args.category:
        wanted = {c.strip() for c in args.category.split(",") if c.strip()}
        selected = [c for c in selected if c.kind.value in wanted]
    if not selected:
        print("선택된 후보 없음.")
        return 0

    dry_run = not args.apply
    results = apply_cleanup(plan, selected=selected, dry_run=dry_run, vault=vault)
    manifest = write_cleanup_manifest(vault, results)

    moved = sum(1 for r in results if r.status == "moved")
    dry = sum(1 for r in results if r.status == "dry_run")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")

    if dry_run:
        print(
            f"dry-run: 이동 예정 {dry}건, 건너뜀 {skipped}건. "
            f"실제 적용은 `--apply`를 붙이세요."
        )
    else:
        print(
            f"이동 {moved}건, 건너뜀 {skipped}건, 실패 {failed}건. "
            f"매니페스트: {manifest}"
        )
    return 0 if failed == 0 else 1


def cmd_me_update_profile(args: argparse.Namespace) -> int:
    """raw → Profile/DecisionPattern 후보 → MemoryInbox PR."""
    args.sample_lines = _arg_or_config(args.sample_lines, "profile.sample_lines", 200)
    args.model = _resolve_model(args.model, "update_profile")
    _enforce_cost_cap("persona update-profile")
    _interactive_guard("persona update-profile", "update-profile")
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
    from synapse_memory.config import get_config as _get_config

    ai_folders = _get_config().vault_folders.system.ai
    print(f"  검토 후 vault {ai_folders.profile}, {ai_folders.decision_patterns} 반영")
    return 0


def cmd_persona_ingest(args: argparse.Namespace) -> int:
    """외부 markdown/txt 파일 → L0 mirror → ProfileFact 후보 → MemoryInbox PR.

    M1b: 회고록 · 일기 · 외부 메모를 흡수해 사용자 성향을 보강한다.
    """
    args.model = _resolve_model(args.model, "update_profile")
    _enforce_cost_cap("persona ingest")
    _interactive_guard("persona ingest", "update-profile")

    paths = [Path(p) for p in args.file]
    try:
        result = ingest_files(paths)
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2

    for f in result.files:
        if f.skipped_reason == "unsupported":
            ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            print(
                f"  SKIPPED (unsupported): {f.source_path.name} "
                f"(지원: {ext_list})",
                file=sys.stderr,
            )
        elif f.skipped_reason == "empty_redacted":
            print(
                f"  SKIPPED (redaction empty): {f.source_path.name} "
                f"— raw 는 L0 에 보존됨, redactlist 조정 후 재시도",
                file=sys.stderr,
            )

    if not result.combined_redacted:
        print(f"{FAIL} 흡수 가능한 텍스트 없음", file=sys.stderr)
        return 1

    print(
        f"INGESTED: {result.accepted_count} files mirrored to L0 private storage"
    )

    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    try:
        print("ProfileFact 추출 중 (외부 자료 기반)...")
        facts = extract_profile_facts(
            sample_lines=0,  # history 무시 — ingest 가 자료의 출처
            model=args.model,
            ai_env=ai_env,
            extra_text=result.combined_redacted,
        )
        print(f"  → {len(facts)} fact 추출")
    except AIError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    path = save_profile_update(facts, patterns=None)
    print(f"\n{OK} MemoryInbox PR 저장: {path}")
    from synapse_memory.config import get_config as _get_config

    profile_path = _get_config().vault_folders.system.ai.profile
    print(f"  검토 후 vault {profile_path} 반영")
    return 0


def cmd_persona_design_project(args: argparse.Namespace) -> int:
    """새 프로젝트 설계 초안 → vault Drafts. M1c.

    Profile (tech/work_style/voice) + ProjectCard RAG 를 종합해 사용자
    스타일이 반영된 설계 markdown 을 ``20_Projects/Drafts/`` 에 저장한다.
    """
    args.top_k = _arg_or_config(args.top_k, "top_k.resume", 6)
    args.model = _resolve_model(args.model, "resume")
    _enforce_cost_cap("persona design-project")
    _interactive_guard("persona design-project", "decide")

    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    from synapse_memory.recipes import (
        InputValidationError,
        RecipeNotFoundError,
        RecipeValidationError,
    )
    from synapse_memory.recipes import (
        generate as recipes_generate,
    )

    store = None
    try:
        store = open_vector_store()
    except (VectorStoreError, EmbeddingUnavailableError):
        store = None  # ProjectCard 없으면 Profile 만으로 진행

    try:
        result = recipes_generate(
            "design_project",
            inputs={"idea": args.idea},
            store=store,
            ai_env=ai_env,
            model_override=args.model,
            top_k_override=args.top_k,
        )
    except RecipeNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except InputValidationError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 3
    except RecipeValidationError as exc:
        print(f"{FAIL} recipe 검증 실패: {exc}", file=sys.stderr)
        return 4
    except (EmbeddingError, AIError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(result.answer_markdown.rstrip() + "\n")
    if result.saved_path:
        sys.stdout.write(f"\n{OK} 설계 초안 저장: {result.saved_path}\n")
    if not result.profile_used:
        sys.stdout.write(
            "\nNOTE: Profile.md 비어있음 — `persona ingest --file` 또는 "
            "`persona update-profile` 먼저 실행 시 사용자 스타일 반영 개선\n"
        )
    if result.source_ids:
        sys.stdout.write(f"  참고 ProjectCard ({len(result.source_ids)}):\n")
        for cid in result.source_ids:
            sys.stdout.write(f"    - {cid}\n")
    sys.stdout.flush()
    return 0


def cmd_me_draft_resume(args: argparse.Namespace) -> int:
    """회사 맞춤 이력서 자동 생성 → vault Drafts."""
    args.top_k = _arg_or_config(args.top_k, "top_k.resume", 6)
    args.model = _resolve_model(args.model, "resume")
    _enforce_cost_cap("persona draft-resume")
    _interactive_guard("persona draft-resume", "resume")
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
    """Recipe-based generator (007-persona-recipes) — persona generate <recipe>."""
    _enforce_cost_cap(f"persona generate {args.recipe}")
    from synapse_memory.recipes import (
        InputValidationError,
        RecipeHybridUnavailableError,
        RecipeNotFoundError,
        RecipePromptTooLargeError,
        RecipeValidationError,
    )
    from synapse_memory.recipes import (
        generate as recipes_generate,
    )

    _interactive_guard(f"persona generate {args.recipe}", f"generate-{args.recipe}")

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
            rag_mode_override=args.rag_mode,
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
    except RecipeHybridUnavailableError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 10
    except (EmbeddingError, AIError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 10

    duration_ms = int((time.monotonic() - t0) * 1000)
    sys.stdout.write(result.answer_markdown.rstrip() + "\n")
    if result.saved_path:
        sys.stdout.write(f"\n[saved] {result.saved_path}\n")
    sys.stdout.flush()
    # recipe source (builtin vs user) — RecipeRegistry 한 번 더 스캔해 source 표시
    recipe_source = "?"
    try:
        from synapse_memory.collectors.obsidian.mirror import get_vault_path
        from synapse_memory.config import get_config
        from synapse_memory.recipes.registry import RecipeRegistry

        _vault = vault_path or get_vault_path()
        _reg = RecipeRegistry(
            builtin_dir=Path(__file__).resolve().parent / "recipes" / "builtin",
            user_dir=_vault / get_config().vault_folders.system.ai.recipes,
        )
        _reg.scan()
        recipe = _reg.recipes.get(result.recipe_name)
        recipe_source = recipe.source if recipe is not None else "?"
    except Exception:  # observability 보조라 silent fallback
        pass

    sys.stderr.write(
        f"[persona.generate.{result.recipe_name}] "
        f"source={recipe_source} "
        f"rag_mode={result.rag_mode} "
        f"locale={result.locale_source}:{result.locale} "
        f"domain={result.domain_source}:{result.domain} "
        f"profile_used={result.profile_used} "
        f"matched={len(result.source_ids)} "
        f"duration={duration_ms}ms\n"
    )
    sys.stderr.flush()
    return 0


def _recipes_registry_for_vault(vault_arg: str | None) -> Any:
    """persona recipes list/show 의 공통 helper — RecipeRegistry 인스턴스 반환."""
    from synapse_memory.config import get_config
    from synapse_memory.recipes.registry import RecipeRegistry

    vault = (
        Path(vault_arg).expanduser().resolve()
        if vault_arg
        else get_obsidian_vault().expanduser().resolve()
    )
    builtin_dir = Path(__file__).resolve().parent / "recipes" / "builtin"
    user_dir = vault / get_config().vault_folders.system.ai.recipes
    reg = RecipeRegistry(builtin_dir=builtin_dir, user_dir=user_dir)
    reg.scan()
    return reg


def _format_recipes_table(recipes: list[Any]) -> str:
    """plain-text 표 — list[GenerationRecipe] → 정렬된 stdout 문자열."""
    headers = ("NAME", "SOURCE", "REQUIRED INPUTS", "DESCRIPTION")
    rows: list[tuple[str, str, str, str]] = [headers]
    for r in recipes:
        rows.append(
            (
                r.name,
                r.source,
                ",".join(r.required_inputs) or "-",
                r.description,
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = ["  ".join(c.ljust(widths[j]) for j, c in enumerate(row)) for row in rows]
    return "\n".join(lines) + "\n"


def _recipes_envelope(
    ok: bool, data: object, errors: Iterable[object] | None = None
) -> str:
    """contracts/cli-contracts.md §5 의 JSON envelope."""
    import json

    payload = {"ok": ok, "data": data, "errors": list(errors or [])}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def cmd_me_recipes_list(args: argparse.Namespace) -> int:
    """persona recipes list — 모든 recipe 표 출력 (builtin + user)."""
    try:
        reg = _recipes_registry_for_vault(args.vault)
    except Exception as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    source_filter = getattr(args, "source", "all")
    items = [
        r for r in reg.list() if source_filter == "all" or r.source == source_filter
    ]

    if getattr(args, "json", False):
        data = [
            {
                "name": r.name,
                "source": r.source,
                "description": r.description,
                "required_inputs": list(r.required_inputs),
                "optional_inputs": list(r.optional_inputs),
                "save_subpath": r.save_subpath,
                "locale_aware": r.locale_aware,
                "domain_aware": r.domain_aware,
            }
            for r in items
        ]
        sys.stdout.write(_recipes_envelope(True, data))
        return 0

    sys.stdout.write(_format_recipes_table(items))
    if getattr(args, "verbose", False) and reg.skipped:
        sys.stdout.write("\n# Skipped\n")
        for path, reason in reg.skipped:
            sys.stdout.write(f"- {path}: {reason}\n")
    return 0


def cmd_me_recipes_show(args: argparse.Namespace) -> int:
    """persona recipes show <recipe> — 한 recipe 의 세부 사항 + system_prompt preview."""
    from synapse_memory.recipes.registry import RecipeNotFoundError

    try:
        reg = _recipes_registry_for_vault(args.vault)
    except Exception as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    try:
        r = reg.get(args.recipe)
    except RecipeNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        if exc.suggestions:
            print(
                "  가까운 후보: " + ", ".join(exc.suggestions), file=sys.stderr
            )
        return 2

    prompt_lines = r.system_prompt.splitlines()
    show_full = getattr(args, "full", False)
    shown_prompt = prompt_lines if show_full else prompt_lines[:20]

    if getattr(args, "json", False):
        data = {
            "name": r.name,
            "source": r.source,
            "source_path": str(r.source_path),
            "description": r.description,
            "required_inputs": list(r.required_inputs),
            "optional_inputs": list(r.optional_inputs),
            "rag_filter": r.rag_filter,
            "rag_top_k": r.rag_top_k,
            "save_subpath": r.save_subpath,
            "use_profile": r.use_profile,
            "locale_aware": r.locale_aware,
            "domain_aware": r.domain_aware,
            "timeout": r.timeout,
            "model": r.model,
            "system_prompt": "\n".join(shown_prompt),
        }
        sys.stdout.write(_recipes_envelope(True, data))
        return 0

    sys.stdout.write(f"name:           {r.name}\n")
    sys.stdout.write(f"source:         {r.source}\n")
    sys.stdout.write(f"source_path:    {r.source_path}\n")
    sys.stdout.write(f"description:    {r.description}\n")
    sys.stdout.write("input_schema:\n")
    for k, req in r.input_schema.items():
        sys.stdout.write(f"  - {k} ({req})\n")
    sys.stdout.write(f"rag_filter:     {r.rag_filter}\n")
    sys.stdout.write(f"rag_top_k:      {r.rag_top_k}\n")
    sys.stdout.write(f"use_profile:    {r.use_profile}\n")
    sys.stdout.write(f"save_subpath:   {r.save_subpath}\n")
    sys.stdout.write(f"locale_aware:   {r.locale_aware}\n")
    sys.stdout.write(f"domain_aware:   {r.domain_aware}\n")
    sys.stdout.write(f"timeout:        {r.timeout}\n")
    sys.stdout.write(f"model:          {r.model}\n\n")
    suffix = " (full):" if show_full else " (first 20 lines):"
    sys.stdout.write(f"system_prompt{suffix}\n")
    for line in shown_prompt:
        sys.stdout.write(line + "\n")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """자연어 질의 → RAG → AI 답변."""
    args.top_k = _arg_or_config(args.top_k, "top_k.ask", 5)
    args.model = _resolve_model(args.model, "ask")
    _enforce_cost_cap("ask")
    _interactive_guard("ask", "ask")
    ai_env = detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for r in ai_env.reasons_unavailable():
            print(f"  - {r}", file=sys.stderr)
        return 2

    where: dict[str, object] | None = None
    if args.kind:
        where = {"source_kind": f"card_{args.kind}"}

    try:
        result = ask(
            args.query,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
            where=where,
            hybrid=args.hybrid,
            save=args.save,
        )
    except (EmbeddingUnavailableError, VectorStoreError, BM25IndexError) as exc:
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
    if result.saved_path is not None:
        print()
        print(f"저장: {result.saved_path}")
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
                    target_kind=target.target_kind,
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
    args.days = _arg_or_config(args.days, "cost.summary_days", 30)
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


def _feedback_action(args: argparse.Namespace) -> FeedbackAction:
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


def _feedback_targets(args: argparse.Namespace) -> list[FeedbackTarget]:
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
    args.top_k = _arg_or_config(args.top_k, "top_k.rag_search", 5)
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
    args.model = _resolve_model(args.model, "card_generate")
    _enforce_cost_cap("card generate")
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
    args.model = _resolve_model(args.model, "classify")
    _enforce_cost_cap("cluster classify")
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


_REDACT_FILE_MAX_BYTES = 1 * 1024 * 1024


def cmd_redact_file(args: argparse.Namespace) -> int:
    """단일 파일을 Pass 1+2로 redact해 stdout 또는 --out 경로에 기록."""
    from synapse_memory.redaction import (
        DEFAULT_PATTERNS,
        build_redactlist_patterns,
        load_redactlist,
        redact_full,
    )
    from synapse_memory.redaction.pass1 import redact as pass1_redact

    path = Path(args.path).expanduser().resolve()
    if not path.is_file():
        print(f"{FAIL} 파일이 없습니다: {path}", file=sys.stderr)
        return 2
    size = path.stat().st_size
    if size > _REDACT_FILE_MAX_BYTES:
        print(
            f"{FAIL} 입력이 1 MB를 초과했습니다 ({size} bytes). 분할 처리 권장.",
            file=sys.stderr,
        )
        return 2
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(
            f"{FAIL} UTF-8 텍스트가 아닙니다 (binary 파일은 skip): {path}",
            file=sys.stderr,
        )
        return 2

    env = detect_environment()
    if env.apfel_path is None:
        print(
            "[warn] apfel 미설치 — Pass 1 (regex + redactlist)만 적용한 결과를 출력합니다.",
            file=sys.stderr,
        )
        items = load_redactlist()
        extra_patterns = build_redactlist_patterns(items)
        patterns = list(DEFAULT_PATTERNS) + list(extra_patterns)
        result = pass1_redact(text, patterns=patterns)
        redacted = result.redacted
    else:
        result = redact_full(text, env=env)
        redacted = result.redacted

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(redacted, encoding="utf-8")
    else:
        sys.stdout.write(redacted)
    return 0


def _setup_vault_path() -> Path:
    """vault 경로 resolver (테스트에서 monkeypatch 가능)."""
    from synapse_memory.config import get_config

    vault = get_config().vault
    if vault is None:
        raise ValueError("config.yaml vault 미설정")
    return Path(vault).expanduser().resolve()


def _setup_registry_path() -> Path:
    """projects.yaml 경로 (테스트에서 monkeypatch 가능)."""
    return Path.home() / ".synapse" / "projects.yaml"


def _setup_profile_patterns_paths(vault: Path) -> tuple[Path, Path]:
    from synapse_memory.config import get_config

    cfg = get_config()
    profile = vault / cfg.vault_folders.system.ai.profile
    patterns = vault / cfg.vault_folders.system.ai.decision_patterns
    return profile, patterns


def _hook_runtime_settings() -> tuple[bool, bool, int]:
    from synapse_memory.config import get_config

    hook = get_config(refresh=True).hook
    return hook.enabled, hook.suggest_register, hook.max_inject_bytes


def _render_hook_settings_cache(*, max_inject_bytes: int | None = None) -> Path:
    from synapse_memory.projects.summary import render_hook_settings_cache

    enabled, suggest_register, configured_max = _hook_runtime_settings()
    return render_hook_settings_cache(
        enabled=enabled,
        suggest_register=suggest_register,
        max_inject_bytes=max_inject_bytes or configured_max,
    )


def cmd_setup(args: argparse.Namespace) -> int:
    """현재 디렉터리 프로젝트에 marker 삽입 + registry 등록."""
    import datetime as _datetime

    from synapse_memory.projects.marker import MarkerParseError, inject_or_replace
    from synapse_memory.projects.registry import (
        ProjectEntry,
        load_registry,
        save_registry,
        upsert_entry,
    )
    from synapse_memory.projects.summary import generate_marker_body, render_context_cache

    vault = _setup_vault_path()
    profile, patterns = _setup_profile_patterns_paths(vault)
    body = generate_marker_body(profile, patterns)
    _, _, max_inject_bytes = _hook_runtime_settings()

    project = Path.cwd().resolve()
    targets_for = {
        "codex": ["AGENTS.md"],
        "agents": ["AGENTS.md"],
        "claude": ["CLAUDE.md"],
        "both": ["AGENTS.md", "CLAUDE.md"],
        "hook": [],
    }["hook" if args.no_marker else args.target]

    if args.dry_run:
        print(f"[dry-run] project: {project}")
        if not targets_for:
            print("  marker: 생성/갱신 안 함 (--no-marker)")
        for name in targets_for:
            target_file = project / name
            status = "신규 생성" if not target_file.is_file() else "갱신"
            print(f"  {status}: {target_file}")
        target = "hook" if args.no_marker else args.target
        print(f"  registry: {_setup_registry_path()} (등록 예정, target={target})")
        return 0

    for name in targets_for:
        target_file = project / name
        try:
            changed, _ = inject_or_replace(target_file, body)
        except MarkerParseError as exc:
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        action = "변경됨" if changed else "동일"
        print(f"  {OK} {target_file} — {action}")

    registry = _setup_registry_path()
    entries = load_registry(registry)
    new = ProjectEntry(
        path=project,
        target="hook" if args.no_marker else args.target,
        registered_at=_datetime.date.today(),
        last_sync=None,
        state="active",
    )
    entries = upsert_entry(entries, new)
    save_registry(entries, registry)
    render_context_cache(profile, patterns, max_bytes=max_inject_bytes)
    _render_hook_settings_cache(max_inject_bytes=max_inject_bytes)
    print(f"  {OK} registry: {registry}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """등록된 모든 프로젝트(또는 --current) marker 갱신."""
    import datetime as _datetime

    from synapse_memory.projects.marker import MarkerParseError, inject_or_replace
    from synapse_memory.projects.registry import (
        ProjectEntry,
        load_registry,
        mark_stale,
        save_registry,
    )
    from synapse_memory.projects.summary import generate_marker_body, render_context_cache

    vault = _setup_vault_path()
    profile, patterns = _setup_profile_patterns_paths(vault)
    body = generate_marker_body(profile, patterns)
    _, _, max_inject_bytes = _hook_runtime_settings()

    registry = _setup_registry_path()
    entries = load_registry(registry)
    if not entries:
        print("등록된 프로젝트가 없습니다. `synapse-memory setup` 먼저 실행하세요.")
        return 0

    if args.current:
        cwd = Path.cwd().resolve()
        entries_to_sync = [e for e in entries if e.path == cwd]
        if not entries_to_sync:
            print(f"{FAIL} 현재 디렉터리가 registry에 없습니다: {cwd}", file=sys.stderr)
            return 2
    else:
        entries_to_sync = list(entries)

    today = _datetime.date.today()
    new_entries = list(entries)
    for entry in entries_to_sync:
        if not entry.path.is_dir():
            new_entries = mark_stale(new_entries, entry.path)
            print(f"  ⚠ stale: {entry.path}", file=sys.stderr)
            continue
        targets_for = {
            "codex": ["AGENTS.md"],
            "agents": ["AGENTS.md"],
            "claude": ["CLAUDE.md"],
            "both": ["AGENTS.md", "CLAUDE.md"],
            "hook": [],
        }[entry.target]
        for name in targets_for:
            target_file = entry.path / name
            try:
                inject_or_replace(target_file, body)
            except MarkerParseError as exc:
                print(f"{FAIL} {exc}", file=sys.stderr)
                return 1
        new_entries = [
            ProjectEntry(
                path=e.path,
                target=e.target,
                registered_at=e.registered_at,
                last_sync=today if e.path == entry.path else e.last_sync,
                state=e.state,
            )
            for e in new_entries
        ]
        print(f"  {OK} sync: {entry.path}")

    save_registry(new_entries, registry)
    cache = render_context_cache(profile, patterns, max_bytes=max_inject_bytes)
    _render_hook_settings_cache(max_inject_bytes=max_inject_bytes)
    print(f"  {OK} context-cache: {cache}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    """hook context cache를 marker 갱신 없이 렌더."""
    if args.action == "render":
        from synapse_memory.projects.summary import render_context_cache

        vault = _setup_vault_path()
        profile, patterns = _setup_profile_patterns_paths(vault)
        out_path = Path(args.out).expanduser().resolve() if args.out else None
        _, _, configured_max = _hook_runtime_settings()
        max_bytes = args.max_bytes if args.max_bytes is not None else configured_max
        cache = render_context_cache(profile, patterns, out_path=out_path, max_bytes=max_bytes)
        _render_hook_settings_cache(max_inject_bytes=max_bytes)
        print(f"{OK} context-cache: {cache}")
        return 0

    print(f"{FAIL} unknown context action: {args.action}", file=sys.stderr)
    return 2


def cmd_hook(args: argparse.Namespace) -> int:
    """Claude Code/Codex SessionStart hook 관리."""
    if args.action == "run":
        from synapse_memory.hooks.session_start import main as hook_main

        return hook_main()

    if args.action == "install":
        from synapse_memory.hooks.install import install_session_hook

        try:
            changed = install_session_hook()
        except ValueError as exc:
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        _refresh_hook_sidecars()
        action = "설치됨" if changed else "이미 설치됨"
        print(f"{OK} Claude Code/Codex SessionStart hook {action}")
        print("  Codex는 첫 실행 전 `/hooks`에서 hook 신뢰 승인이 필요할 수 있습니다.")
        return 0

    if args.action == "uninstall":
        from synapse_memory.hooks.install import uninstall_session_hook

        try:
            changed = uninstall_session_hook()
        except ValueError as exc:
            print(f"{FAIL} {exc}", file=sys.stderr)
            return 1
        action = "제거됨" if changed else "설치 항목 없음"
        print(f"{OK} Claude Code/Codex SessionStart hook {action}")
        return 0

    print(f"{FAIL} unknown hook action: {args.action}", file=sys.stderr)
    return 2


def _refresh_hook_sidecars() -> None:
    """hook install 시 기존 registry/cache sidecar를 best-effort 갱신."""
    with contextlib.suppress(Exception):
        from synapse_memory.projects.registry import load_registry, save_registry

        registry = _setup_registry_path()
        if registry.is_file():
            save_registry(load_registry(registry), registry)

    with contextlib.suppress(Exception):
        from synapse_memory.projects.summary import render_context_cache

        vault = _setup_vault_path()
        profile, patterns = _setup_profile_patterns_paths(vault)
        _, _, max_inject_bytes = _hook_runtime_settings()
        render_context_cache(profile, patterns, max_bytes=max_inject_bytes)
        _render_hook_settings_cache(max_inject_bytes=max_inject_bytes)


def cmd_moc(args: argparse.Namespace) -> int:
    """vault 90_System/AI/MOC.md 생성·갱신 (Obsidian Graph 진입점)."""
    from synapse_memory.collectors.obsidian import get_vault_path
    from synapse_memory.moc import write_or_update_moc

    vault = (
        Path(args.vault).expanduser().resolve()
        if args.vault
        else get_vault_path()
    )
    if not vault.is_dir():
        print(f"{FAIL} vault 경로가 존재하지 않습니다: {vault}", file=sys.stderr)
        return 2

    path = write_or_update_moc(vault)
    print(f"{OK} MOC 갱신: {path}")
    print(
        "  Dataview 미설치 시 동적 인덱스가 동작하지 않습니다. "
        "`synapse-memory doctor` 로 점검하세요."
    )
    return 0


def cmd_list_pending_profiles(args: argparse.Namespace) -> int:
    """vault MemoryInbox의 status=pending_review 후보 파일 목록 출력."""
    import json as _json
    import re as _re

    from synapse_memory.collectors.obsidian import get_vault_path
    from synapse_memory.config import get_config
    from synapse_memory.folders import find_candidate_files

    vault = (
        Path(args.vault).expanduser().resolve()
        if args.vault
        else get_vault_path()
    )
    if not vault.is_dir():
        print(f"{FAIL} vault 경로가 존재하지 않습니다: {vault}", file=sys.stderr)
        return 2

    inbox = vault / get_config().vault_folders.system.ai.memory_inbox
    candidates = find_candidate_files(inbox, pattern="Profile-*.md")

    date_pattern = _re.compile(r"^Profile-(\d{4})-(\d{2})-(\d{2})\.md$")
    pending: list[dict[str, str]] = []
    for path in candidates:
        m = date_pattern.match(path.name)
        if m is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "\nstatus: applied" in text or text.startswith("status: applied"):
            continue
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        status = "pending_review"
        if "\nstatus: " in text:
            for line in text.splitlines():
                if line.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                    break
        if status == "applied":
            continue
        pending.append({"date": date, "path": str(path), "status": status})

    pending.sort(key=lambda x: x["date"])

    if args.json:
        sys.stdout.write(_json.dumps(pending, ensure_ascii=False))
        return 0

    if not pending:
        print("pending 후보가 없습니다.")
        return 0
    for entry in pending:
        print(f"{entry['date']} — {entry['path']}")
    return 0


def cmd_dismiss_profile(args: argparse.Namespace) -> int:
    """ProfileFact/DecisionPattern 후보를 dismissed 목록에 append."""
    from synapse_memory.collectors.obsidian import get_vault_path
    from synapse_memory.profile.dismissed import append_dismissed, dismissed_path

    vault = (
        Path(args.vault).expanduser().resolve()
        if args.vault
        else get_vault_path()
    )
    if not vault.is_dir():
        print(f"{FAIL} vault 경로가 존재하지 않습니다: {vault}", file=sys.stderr)
        return 2

    target = dismissed_path(vault)
    record = append_dismissed(
        args.kind,
        args.text,
        reason=args.reason,
        note=args.note,
        path=target,
    )

    if record is None:
        if not args.text.strip():
            print(f"{FAIL} --text 가 비어 있습니다.", file=sys.stderr)
            return 2
        print(
            f"{OK} 이미 dismissed 목록에 있음 (멱등): kind={args.kind} "
            f"text={args.text!r}"
        )
        return 0

    reason_note = f" reason={record.reason}" if record.reason else ""
    print(
        f"{OK} dismissed 추가: kind={record.kind} dismissed_at={record.dismissed_at}"
        f"{reason_note}\n"
        f"     fingerprint={record.fingerprint!r}\n"
        f"     file={target}\n"
        f"     해제하려면 위 파일에서 해당 라인을 삭제하거나, "
        f"profile.dismissed_ttl_days 일 경과를 기다리면 자동 재노출됩니다."
    )
    return 0


# ---------------------------------------------------------------------------
# dismiss-list / dismiss-purge-expired / ledger-show — 관찰성
# ---------------------------------------------------------------------------


def _resolve_vault_or_exit(args: argparse.Namespace) -> Path:
    """공통 vault 인자 해석. 디렉토리 없으면 exit 2 (caller 에서 sys.exit 호출)."""
    from synapse_memory.collectors.obsidian import get_vault_path

    vault = (
        Path(args.vault).expanduser().resolve() if args.vault else get_vault_path()
    )
    if not vault.is_dir():
        print(f"{FAIL} vault 경로가 존재하지 않습니다: {vault}", file=sys.stderr)
        raise SystemExit(2)
    return vault


def cmd_dismiss_list(args: argparse.Namespace) -> int:
    """dismissed.jsonl 조회 — kind/reason/active 필터링."""
    import datetime as _dt
    import json as _json

    from synapse_memory.config import get_config
    from synapse_memory.profile.dismissed import (
        DismissedRecord,
        _ttl_for,
        dismissed_path,
        profile_to_ttl_overrides,
    )

    vault = _resolve_vault_or_exit(args)
    target = dismissed_path(vault)
    if not target.is_file():
        if args.json:
            sys.stdout.write("[]")
        else:
            print("dismissed 목록이 비어 있습니다.")
        return 0

    cfg = get_config().profile
    overrides = profile_to_ttl_overrides(cfg)
    today = _dt.date.today()

    rows: list[dict[str, object]] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        rec = DismissedRecord.from_dict(obj)
        if rec is None:
            continue
        if args.kind != "all" and rec.kind != args.kind:
            continue
        if args.reason is not None and rec.reason != args.reason:
            continue
        ttl = _ttl_for(rec.reason, cfg.dismissed_ttl_days, overrides)
        age_days: int | None = None
        expired = False
        try:
            d = _dt.date.fromisoformat(rec.dismissed_at)
            age_days = (today - d).days
            if ttl > 0 and age_days > ttl:
                expired = True
        except ValueError:
            pass
        if args.active_only and expired:
            continue
        rows.append(
            {
                "kind": rec.kind,
                "fingerprint": rec.fingerprint,
                "original": rec.original,
                "dismissed_at": rec.dismissed_at,
                "reason": rec.reason,
                "note": rec.note,
                "ttl_days": ttl,
                "age_days": age_days,
                "expired": expired,
            }
        )

    if args.json:
        sys.stdout.write(_json.dumps(rows, ensure_ascii=False))
        return 0

    if not rows:
        print("조건에 맞는 dismissed 항목이 없습니다.")
        return 0

    print(f"총 {len(rows)}건 (vault: {vault}, file: {target.name})")
    print("-" * 90)
    for r in rows:
        flag = " [만료]" if r["expired"] else ""
        reason = r["reason"] or "—"
        age = r["age_days"]
        age_s = f"{age}일 전" if age is not None else "?"
        original = str(r["original"])[:60]
        if len(str(r["original"])) > 60:
            original += "…"
        print(
            f"[{r['kind']}] reason={reason:<14} age={age_s:>8} "
            f"ttl={r['ttl_days']}일{flag}\n"
            f"     {original}"
        )
    return 0


def cmd_dismiss_purge_expired(args: argparse.Namespace) -> int:
    """TTL 만료된 dismissed 라인 물리 삭제 (백업 후). dry-run 기본."""
    import datetime as _dt
    import json as _json
    import shutil as _shutil

    from synapse_memory.config import get_config
    from synapse_memory.profile.dismissed import (
        DismissedRecord,
        _ttl_for,
        dismissed_path,
        profile_to_ttl_overrides,
    )

    vault = _resolve_vault_or_exit(args)
    target = dismissed_path(vault)
    if not target.is_file():
        print("dismissed.jsonl 파일이 없습니다.")
        return 0

    cfg = get_config().profile
    overrides = profile_to_ttl_overrides(cfg)
    today = _dt.date.today()

    keep_lines: list[str] = []
    expired_records: list[DismissedRecord] = []
    invalid_kept = 0
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            keep_lines.append(line)
            continue
        try:
            obj = _json.loads(line)
        except _json.JSONDecodeError:
            keep_lines.append(line)  # 깨진 라인은 보존 (사용자 검토용)
            invalid_kept += 1
            continue
        rec = DismissedRecord.from_dict(obj) if isinstance(obj, dict) else None
        if rec is None:
            keep_lines.append(line)
            invalid_kept += 1
            continue
        ttl = _ttl_for(rec.reason, cfg.dismissed_ttl_days, overrides)
        try:
            d = _dt.date.fromisoformat(rec.dismissed_at)
            age = (today - d).days
        except ValueError:
            keep_lines.append(line)  # dismissed_at 깨졌으면 그대로 보존
            continue
        if ttl > 0 and age > ttl:
            expired_records.append(rec)
        else:
            keep_lines.append(line)

    if not expired_records:
        print(
            f"만료된 라인 없음 (총 {len(keep_lines)}건 유효, invalid {invalid_kept}건)"
        )
        return 0

    print(f"만료 대상: {len(expired_records)}건 (유지 {len(keep_lines)}건)")
    for rec in expired_records[:20]:
        original = rec.original[:50] + ("…" if len(rec.original) > 50 else "")
        print(
            f"  [{rec.kind}] reason={rec.reason or '—'} "
            f"dismissed_at={rec.dismissed_at} — {original}"
        )
    if len(expired_records) > 20:
        print(f"  ... ({len(expired_records) - 20}건 더)")

    if not args.apply:
        print(
            f"\n{OK} dry-run — 실제 삭제하려면 `--apply` 추가. "
            "백업 파일이 자동 생성됩니다."
        )
        return 0

    backup = target.with_suffix(
        target.suffix + f".bak.{today.isoformat()}"
    )
    _shutil.copy2(target, backup)
    new_content = "\n".join(keep_lines) + ("\n" if keep_lines else "")
    target.write_text(new_content, encoding="utf-8")
    print(
        f"\n{OK} {len(expired_records)}건 삭제 완료. "
        f"백업: {backup.name}"
    )
    return 0


def cmd_ledger_show(args: argparse.Namespace) -> int:
    """profile_ledger.jsonl 조회 — promotion 상태 + 통계."""
    import json as _json

    from synapse_memory.profile.ledger import LedgerEntry, ledger_path, load_ledger

    target = ledger_path()
    if not target.is_file():
        if args.json:
            sys.stdout.write("[]")
        else:
            print("ledger 파일 없음 — 아직 update_profile 호출이 없습니다.")
        return 0

    ledger = load_ledger()
    entries: list[LedgerEntry] = list(ledger.values())
    if args.kind != "all":
        entries = [e for e in entries if e.kind == args.kind]
    if args.status == "promoted":
        entries = [e for e in entries if e.promoted]
    elif args.status == "awaiting":
        entries = [e for e in entries if not e.promoted]

    entries.sort(key=lambda e: (-e.seen_count, -e.peak_confidence()))
    if args.top and args.top > 0:
        entries = entries[: args.top]

    if args.json:
        sys.stdout.write(
            _json.dumps([e.to_dict() for e in entries], ensure_ascii=False)
        )
        return 0

    if not entries:
        print("조건에 맞는 ledger 항목이 없습니다.")
        return 0

    # 요약 stat
    total = len(ledger)
    promoted = sum(1 for e in ledger.values() if e.promoted)
    awaiting = total - promoted
    print(
        f"ledger 총 {total}건 (promoted {promoted} / awaiting {awaiting}). "
        f"표시: {len(entries)}건 (kind={args.kind}, status={args.status})"
    )
    print("-" * 90)
    for e in entries:
        flag = "✓ promoted" if e.promoted else "  awaiting"
        snippet = e.best_statement()[:60]
        if len(e.best_statement()) > 60:
            snippet += "…"
        print(
            f"[{e.kind}] {flag}  seen={e.seen_count:>3}  "
            f"peak={e.peak_confidence():.2f}  avg={e.aggregated_confidence():.2f}  "
            f"({e.first_seen} → {e.last_seen})\n"
            f"     {snippet}"
        )
    return 0


def cmd_profile_review_awaiting(args: argparse.Namespace) -> int:
    """ledger awaiting 중 peak ≥ ``--min-confidence`` 인 항목을 promote.

    daily 종료 후 "신규 fact/pattern 0건" 으로 끝났지만 ledger 에 의미 있는
    awaiting 후보가 있을 때, 사용자가 명시적으로 임계치를 완화해 검토하고
    싶을 때 호출. dedupe/dismissed 안전망은 그대로 적용.
    """
    from synapse_memory.collectors.obsidian.mirror import get_vault_path
    from synapse_memory.config import get_config
    from synapse_memory.profile.dedupe import dedupe_against_vault
    from synapse_memory.profile.dismissed import dismissed_path, load_dismissed
    from synapse_memory.profile.extract import save_profile_update
    from synapse_memory.profile.ledger import (
        collect_review_candidates,
        load_ledger,
        mark_promoted,
        save_ledger,
    )

    cfg = get_config()
    vault = get_vault_path()
    ai = cfg.vault_folders.system.ai
    profile_path = vault / ai.profile
    dp_path = vault / ai.decision_patterns
    dismissed = load_dismissed(dismissed_path(vault))

    ledger = load_ledger()
    if not ledger:
        print("ledger 비어있음 — 먼저 'synapse-memory daily' 를 실행하세요.")
        return 0

    window_days = cfg.profile.promotion_window_days
    min_conf = args.min_confidence

    candidate_facts, candidate_patterns = collect_review_candidates(
        ledger, min_confidence=min_conf, window_days=window_days,
    )

    if not candidate_facts and not candidate_patterns:
        print(
            f"임계치 peak ≥ {min_conf:.2f} & window {window_days}일 내 awaiting "
            "항목 없음."
        )
        return 0

    facts, patterns, report = dedupe_against_vault(
        candidate_facts,
        candidate_patterns,
        profile_path=profile_path,
        decision_patterns_path=dp_path,
        dismissed_facts=dismissed.facts,
        dismissed_patterns=dismissed.patterns,
    )

    if args.dry_run:
        print(
            f"[dry-run] 후보 fact={len(facts)} pattern={len(patterns)} "
            f"(dedupe 제외 -{report.total_dropped}) — peak ≥ {min_conf:.2f}"
        )
        for f in facts[:10]:
            print(f"  fact    [{f.confidence:.2f}] {f.statement[:80]}")
        for p in patterns[:10]:
            print(f"  pattern [{p.confidence:.2f}] {p.trigger[:80]}")
        return 0

    if not facts and not patterns:
        print("dedupe 후 남은 후보 없음 (vault 또는 dismissed 와 중복).")
        return 0

    mark_promoted(ledger, facts, patterns)
    save_ledger(ledger)
    path = save_profile_update(facts, patterns, ledger=ledger)
    print(
        f"{OK} fact={len(facts)} pattern={len(patterns)} → {path.name} "
        f"(peak ≥ {min_conf:.2f}, vault dedupe -{report.total_dropped})"
    )
    return 0


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
    p_doctor.add_argument("--fix", action="store_true", help="whitelist 기반 자동 복구")
    p_doctor.add_argument(
        "--fix-config",
        action="store_true",
        help="config.yaml vault 경로를 detection 결과로 갱신 (별도 명시 필요, --fix와 분리)",
    )
    p_doctor.add_argument(
        "--yes",
        action="store_true",
        help="doctor --fix preview 후 짧은 대기 생략",
    )
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

    p_redact_file = redact_sub.add_parser(
        "file", help="단일 파일을 Pass 1+2로 redact해 stdout/--out에 출력"
    )
    p_redact_file.add_argument("path", help="redact할 입력 파일 경로")
    p_redact_file.add_argument(
        "--out",
        default=None,
        help="결과 저장 경로 (미지정 시 stdout)",
    )
    p_redact_file.set_defaults(func=cmd_redact_file)

    p_setup = sub.add_parser(
        "setup",
        help="현재 디렉터리에 SYNAPSE-MEMORY marker 삽입 + ~/.synapse/projects.yaml 등록",
    )
    p_setup.add_argument(
        "--target",
        choices=("agents", "claude", "both", "codex"),
        default="both",
        help="대상 파일 (기본: both)",
    )
    p_setup.add_argument(
        "--no-marker",
        action="store_true",
        help="AGENTS.md/CLAUDE.md 수정 없이 registry와 hook cache만 등록",
    )
    p_setup.add_argument(
        "--dry-run",
        action="store_true",
        help="의도된 변경만 출력, 파일/registry 변경 X",
    )
    p_setup.set_defaults(func=cmd_setup)

    p_sync = sub.add_parser(
        "sync",
        help="등록된 모든 프로젝트의 SYNAPSE-MEMORY marker 갱신",
    )
    p_sync.add_argument(
        "--current",
        action="store_true",
        help="cwd 프로젝트만 갱신 (기본: 등록 전체)",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_context = sub.add_parser(
        "context",
        help="hook context cache 관리",
    )
    context_sub = p_context.add_subparsers(
        dest="action", required=True, metavar="ACTION"
    )
    p_context_render = context_sub.add_parser(
        "render",
        help="Profile/DecisionPatterns hook context cache 렌더",
    )
    p_context_render.add_argument(
        "--out",
        default=None,
        help="출력 경로 override (기본: ~/.synapse/context/rendered.md)",
    )
    p_context_render.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="렌더 결과 byte 상한 (기본: 2048)",
    )
    p_context_render.set_defaults(func=cmd_context)

    p_hook = sub.add_parser("hook", help="Claude Code/Codex SessionStart hook 관리")
    hook_sub = p_hook.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_hook_install = hook_sub.add_parser("install", help="SessionStart hook 설치")
    p_hook_install.set_defaults(func=cmd_hook)

    p_hook_uninstall = hook_sub.add_parser("uninstall", help="SessionStart hook 제거")
    p_hook_uninstall.set_defaults(func=cmd_hook)

    p_hook_run = hook_sub.add_parser("run", help="SessionStart hook 실행")
    p_hook_run.add_argument(
        "--event",
        choices=("session-start",),
        required=True,
        help="hook event 이름",
    )
    p_hook_run.set_defaults(func=cmd_hook)

    p_moc = sub.add_parser(
        "moc",
        help="vault 90_System/AI/MOC.md 생성·갱신 (Obsidian Graph 진입점)",
    )
    p_moc.add_argument(
        "--vault",
        default=None,
        help="vault 경로 override (기본: config)",
    )
    p_moc.set_defaults(func=cmd_moc)

    p_list_pending = sub.add_parser(
        "list-pending-profiles",
        help="vault MemoryInbox의 status=pending_review 후보 파일 목록",
    )
    p_list_pending.add_argument(
        "--vault",
        default=None,
        help="vault 경로 override (기본: config)",
    )
    p_list_pending.add_argument(
        "--json",
        action="store_true",
        help="JSON 배열로 출력 (슬래시 prompt가 파싱하기 좋게)",
    )
    p_list_pending.set_defaults(func=cmd_list_pending_profiles)

    p_dismiss = sub.add_parser(
        "dismiss-profile",
        help="ProfileFact/DecisionPattern 후보를 dismissed 목록에 추가 "
        "(다음 daily 부터 재추출 차단; TTL 후 자동 해제)",
    )
    p_dismiss.add_argument(
        "--kind",
        choices=("fact", "pattern"),
        required=True,
        help="fact: ProfileFact, pattern: DecisionPattern",
    )
    p_dismiss.add_argument(
        "--text",
        required=True,
        help="dismiss 할 원문 (fact statement 또는 pattern trigger)",
    )
    p_dismiss.add_argument(
        "--reason",
        default="",
        choices=("", "one_time", "misclassified", "user_changed", "irrelevant", "other"),
        help=(
            "dismiss 이유 — 미지정 시 빈 문자열. "
            "one_time: 1회성 작업, misclassified: LLM 오추출, "
            "user_changed: 사용자 성향 변경, irrelevant: 관련 없음, other: 기타"
        ),
    )
    p_dismiss.add_argument(
        "--note",
        default="",
        help="reason=other 일 때 자유 텍스트 메모 (선택)",
    )
    p_dismiss.add_argument(
        "--vault",
        default=None,
        help="vault 경로 override (기본: config)",
    )
    p_dismiss.set_defaults(func=cmd_dismiss_profile)

    p_dismiss_list = sub.add_parser(
        "dismiss-list",
        help="dismissed 목록 조회 (reason / kind / 만료 필터)",
    )
    p_dismiss_list.add_argument(
        "--kind",
        choices=("fact", "pattern", "all"),
        default="all",
        help="필터 (기본 all)",
    )
    p_dismiss_list.add_argument(
        "--reason",
        default=None,
        choices=("", "one_time", "misclassified", "user_changed",
                 "irrelevant", "other"),
        help="reason 필터 (미지정 시 전체; 빈 문자열은 '미상' 라인만)",
    )
    p_dismiss_list.add_argument(
        "--active-only",
        action="store_true",
        help="만료되지 않은 라인만 (TTL 정책 적용)",
    )
    p_dismiss_list.add_argument(
        "--json",
        action="store_true",
        help="JSON 배열로 출력 (스킬/스크립트용)",
    )
    p_dismiss_list.add_argument(
        "--vault",
        default=None,
        help="vault 경로 override (기본: config)",
    )
    p_dismiss_list.set_defaults(func=cmd_dismiss_list)

    p_dismiss_purge = sub.add_parser(
        "dismiss-purge-expired",
        help="TTL 만료된 dismissed 라인을 물리적으로 제거 (백업 후)",
    )
    p_dismiss_purge.add_argument(
        "--dry-run",
        action="store_true",
        help="삭제 대상만 출력하고 파일은 건드리지 않음 (default)",
    )
    p_dismiss_purge.add_argument(
        "--apply",
        action="store_true",
        help="실제 삭제 수행 (--dry-run 우선)",
    )
    p_dismiss_purge.add_argument(
        "--vault",
        default=None,
        help="vault 경로 override (기본: config)",
    )
    p_dismiss_purge.set_defaults(func=cmd_dismiss_purge_expired)

    p_ledger_show = sub.add_parser(
        "ledger-show",
        help="profile_ledger.jsonl 조회 (promotion 대기/완료 + reason 통계)",
    )
    p_ledger_show.add_argument(
        "--kind",
        choices=("fact", "pattern", "all"),
        default="all",
    )
    p_ledger_show.add_argument(
        "--status",
        choices=("all", "promoted", "awaiting"),
        default="all",
        help="promoted 만 / awaiting 만 / 전체",
    )
    p_ledger_show.add_argument(
        "--top",
        type=int,
        default=20,
        help="seen_count 내림차순 상위 N (기본 20). 0=전체",
    )
    p_ledger_show.add_argument(
        "--json",
        action="store_true",
        help="JSON 배열로 출력",
    )
    p_ledger_show.set_defaults(func=cmd_ledger_show)

    p_review_awaiting = sub.add_parser(
        "profile-review-awaiting",
        help=(
            "ledger awaiting 중 peak ≥ --min-confidence 인 항목을 promote — "
            "daily 가 0건으로 끝났을 때 임계치 완화 검토용"
        ),
    )
    p_review_awaiting.add_argument(
        "--min-confidence",
        type=float,
        default=0.85,
        help="peak confidence 임계치 (기본 0.85)",
    )
    p_review_awaiting.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 promote 없이 후보만 출력",
    )
    p_review_awaiting.set_defaults(func=cmd_profile_review_awaiting)

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
        default=None,
        help="AI 모델 (생략 시 config.models.card_generate — 기본 sonnet)",
    )
    p_card_gen.add_argument(
        "--force", action="store_true", help="기존 Card 덮어쓰기"
    )
    p_card_gen.set_defaults(func=cmd_card_generate)

    p_wiki = sub.add_parser("wiki", help="wiki-first 검색 + 답변 환원")
    wiki_sub = p_wiki.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_wiki_ask = wiki_sub.add_parser("ask", help="wiki 근거 질의 (인용 포함)")
    p_wiki_ask.add_argument("query", help="자연어 질의")
    p_wiki_ask.add_argument(
        "--save", action="store_true", help="답변을 insight 페이지로 환원"
    )
    p_wiki_ask.set_defaults(func=cmd_wiki_ask)

    p_wiki_reindex = wiki_sub.add_parser("reindex", help="모든 wiki 페이지 재인덱싱")
    p_wiki_reindex.set_defaults(func=cmd_wiki_reindex)

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
        default=None,
        help="AI 모델 (생략 시 config.models.classify — 기본 haiku)",
    )
    p_cl_class.set_defaults(func=cmd_cluster_classify)

    p_rag = sub.add_parser("rag", help="벡터 검색 (RAG)")
    rag_sub = p_rag.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_rag_idx = rag_sub.add_parser("index", help="Card → 벡터 DB 인덱싱")
    p_rag_idx.add_argument(
        "--rebuild", action="store_true", help="기존 collection 비우고 처음부터"
    )
    p_rag_idx.add_argument(
        "--include-raw",
        action="store_true",
        help="10_Active와 redacted Claude Code raw chunks까지 인덱싱",
    )
    p_rag_idx.set_defaults(func=cmd_rag_index)

    p_rag_search = rag_sub.add_parser("search", help="자연어 query → top-k Card")
    p_rag_search.add_argument("query", help="검색 자연어")
    p_rag_search.add_argument("--top-k", type=int, default=None)
    p_rag_search.add_argument(
        "--show-snippet", action="store_true", help="결과 본문 일부 출력"
    )
    p_rag_search.set_defaults(func=cmd_rag_search)

    p_ask = sub.add_parser(
        "ask", help="자연어 질의 → RAG retrieve → AI 답변"
    )
    p_ask.add_argument("query", help="자연어 질문")
    p_ask.add_argument("--top-k", type=int, default=None)
    p_ask.add_argument("--model", default=None)
    p_ask.add_argument(
        "--kind",
        choices=["project", "company"],
        help="특정 Card 종류만 retrieve",
    )
    p_ask.add_argument(
        "--hybrid",
        action="store_true",
        help="dense + BM25 RRF 결합 검색",
    )
    p_ask.add_argument(
        "--save",
        action="store_true",
        help="답변을 InsightCard로 저장",
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
    p_cost_summary.add_argument("--days", type=int, default=None)
    p_cost_summary.add_argument("--by", choices=("command", "model"), default="command")
    p_cost_summary.add_argument("--json", action="store_true", help="JSON 출력")
    p_cost_summary.set_defaults(func=cmd_cost_summary)

    p_me = sub.add_parser("persona", help="Persona 통합 endpoints (이전 'me')")
    me_sub = p_me.add_subparsers(dest="action", required=True, metavar="ACTION")
    p_resume = me_sub.add_parser(
        "draft-resume", help="회사 맞춤 이력서 자동 작성"
    )
    p_resume.add_argument(
        "company_id",
        help="CompanyCard 파일명 슬러그 (예: danggeun, 샘플회사)",
    )
    p_resume.add_argument("--top-k", type=int, default=None)
    p_resume.add_argument("--model", default=None)
    p_resume.set_defaults(func=cmd_me_draft_resume)

    p_up = me_sub.add_parser(
        "update-profile",
        help="raw → ProfileFact/DecisionPattern 후보 → MemoryInbox PR",
    )
    p_up.add_argument(
        "--sample-lines",
        type=int,
        default=None,
        help="history.jsonl 마지막 N줄 분석 (생략 시 config.profile.sample_lines)",
    )
    p_up.add_argument("--model", default=None)
    p_up.add_argument(
        "--facts-only",
        action="store_true",
        help="DecisionPattern 추출 skip (비용 절감)",
    )
    p_up.set_defaults(func=cmd_me_update_profile)

    p_ingest = me_sub.add_parser(
        "ingest",
        help="외부 markdown/txt 흡수 → L0 mirror + ProfileFact 후보 → MemoryInbox PR",
    )
    p_ingest.add_argument(
        "--file",
        action="append",
        required=True,
        metavar="PATH",
        help="흡수할 파일 (반복 가능). 지원 확장자: .md, .markdown, .txt",
    )
    p_ingest.add_argument("--model", default=None)
    p_ingest.set_defaults(func=cmd_persona_ingest)

    p_dp = me_sub.add_parser(
        "design-project",
        help="새 프로젝트 설계 초안 — Profile + ProjectCard 기반 (M1c)",
    )
    p_dp.add_argument("idea", help="프로젝트 아이디어 한 줄 (예: 'iOS Todo 앱')")
    p_dp.add_argument("--top-k", type=int, default=None)
    p_dp.add_argument("--model", default=None)
    p_dp.set_defaults(func=cmd_persona_design_project)

    p_wdt = me_sub.add_parser(
        "what-did-i-think", help="주제에 대한 과거 사고 회상"
    )
    p_wdt.add_argument("topic", help="회상할 주제")
    p_wdt.add_argument("--top-k", type=int, default=None)
    p_wdt.add_argument("--model", default=None)
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
    p_wdt.add_argument(
        "--hybrid",
        action="store_true",
        help="distance 모드에서 dense + BM25 RRF 결합 검색",
    )
    p_wdt.set_defaults(func=cmd_me_what_did_i_think)

    p_dec = me_sub.add_parser(
        "decide", help="의사결정 코파일럿 (Profile + Patterns + RAG)"
    )
    p_dec.add_argument("situation", help="결정할 상황")
    p_dec.add_argument("--top-k", type=int, default=None)
    p_dec.add_argument("--model", default=None)
    p_dec.set_defaults(func=cmd_me_decide)

    p_gen = me_sub.add_parser(
        "generate",
        help="recipe 기반 결과물 생성 (007-persona-recipes: weekly_report / journal / ...)",
    )
    p_gen.add_argument("recipe", help="recipe 이름 (persona recipes list 로 확인 — 추후)")
    p_gen.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="recipe input_schema 의 key=value (여러 번 지정 가능)",
    )
    p_gen.add_argument("--language", default=None, help="locale precedence 0 순위")
    p_gen.add_argument("--domain", default=None, help="domain precedence 0 순위")
    p_gen.add_argument(
        "--rag-mode",
        choices=("dense", "hybrid"),
        default=None,
        help="recipe rag_mode 기본값 override",
    )
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

    p_recipes = me_sub.add_parser(
        "recipes",
        help="recipe 목록·상세 (007-persona-recipes)",
    )
    recipes_sub = p_recipes.add_subparsers(
        dest="recipes_action", required=True, metavar="RECIPES_ACTION"
    )
    p_recipes_list = recipes_sub.add_parser(
        "list", help="모든 recipe 표 출력 (builtin + user)"
    )
    p_recipes_list.add_argument(
        "--source", choices=("builtin", "user", "all"), default="all"
    )
    p_recipes_list.add_argument("--vault", default=None)
    p_recipes_list.add_argument(
        "--verbose", action="store_true", help="검증 실패 recipe 도 표시"
    )
    p_recipes_list.add_argument(
        "--json", action="store_true", help="machine-readable JSON envelope"
    )
    p_recipes_list.set_defaults(func=cmd_me_recipes_list)

    p_recipes_show = recipes_sub.add_parser(
        "show", help="recipe 1 건 상세 + system_prompt preview"
    )
    p_recipes_show.add_argument("recipe", help="recipe 이름")
    p_recipes_show.add_argument("--vault", default=None)
    p_recipes_show.add_argument("--json", action="store_true")
    p_recipes_show.add_argument(
        "--full", action="store_true", help="system_prompt 전체 출력"
    )
    p_recipes_show.set_defaults(func=cmd_me_recipes_show)

    p_daily = sub.add_parser("daily", help="일일 통합 파이프라인 (5분 워크플로)")
    p_daily.add_argument(
        "--only",
        help=f"이 단계들만 (comma-separated). 가능: {','.join(STEPS)}",
    )
    p_daily.add_argument("--skip", help="제외할 단계 (comma-separated)")
    p_daily.add_argument(
        "--resume-from",
        choices=STEPS,
        help="지정 stage부터 daily 재개",
    )
    # default=None — CLI 인자가 명시되지 않으면 cmd_daily에서
    # _resolve_model() 로 config.models.<provider>.<task> 를 따른다.
    p_daily.add_argument("--classify-model", default=None)
    p_daily.add_argument("--generate-model", default=None)
    p_daily.add_argument("--profile-model", default=None)
    p_daily.add_argument("--profile-sample-lines", type=int, default=200)
    p_daily.add_argument("--profile-facts-only", action="store_true")
    p_daily.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Quick mode — 최근 N일 modified 노트만 처리 + classify cluster 수 제한 "
            "+ update_profile auto-skip. 첫 답변 ~3분 목표. full pipeline 은 "
            "별도 cron 또는 수동 `daily` (no flag) 호출 (ChromaDB 동시성 회피)."
        ),
    )
    p_daily.add_argument(
        "--quick-days",
        type=int,
        default=7,
        help="--quick 모드의 mtime cutoff 일수 (기본 7)",
    )
    p_daily.add_argument(
        "--quick-max-clusters",
        type=int,
        default=10,
        help="--quick 모드의 classify 최대 cluster 수 (기본 10)",
    )
    p_daily.add_argument(
        "--watch-status",
        action="store_true",
        help="daily 실행 중 status 파일을 폴링해 stage 진행률을 한 줄씩 출력",
    )
    p_daily.add_argument(
        "--status-interval",
        type=float,
        default=2.0,
        help="--watch-status 폴링 주기(초, 최소 0.5)",
    )
    p_daily.add_argument("--dry-run", action="store_true", help="실행 안 하고 단계만")
    p_daily.set_defaults(func=cmd_daily)

    p_ingest = sub.add_parser("ingest", help="wiki ingest 엔진 (raw 대화 → wiki 통합)")
    p_ingest.add_argument("--now", action="store_true", help="즉시 1회 ingest")
    p_ingest.add_argument("--source", default="claude-code", choices=["claude-code"],
                          help="ingest 소스 (P1a: claude-code)")
    p_ingest.add_argument("--dry-run", action="store_true", help="적용 없이 결과만 표시")
    p_ingest.add_argument("--limit", type=int, default=None, help="처리할 최대 doc 수")
    p_ingest.set_defaults(func=cmd_ingest)

    p_daily_status = sub.add_parser(
        "daily-status",
        help="진행 중인/마지막 daily 진행률 조회 (~/.synapse/run/daily.status.json)",
    )
    p_daily_status.add_argument(
        "--json", action="store_true", help="JSON 원본 그대로 출력"
    )
    p_daily_status.add_argument(
        "--watch",
        action="store_true",
        help="2초 간격으로 폴링하여 상태 변화 추적",
    )
    p_daily_status.add_argument(
        "--interval", type=float, default=2.0, help="--watch 폴링 주기(초)"
    )
    p_daily_status.set_defaults(func=cmd_daily_status)

    p_config = sub.add_parser(
        "config",
        help="사용자 설정 관리 (~/.synapse/config.yaml)",
    )
    config_sub = p_config.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_cfg_show = config_sub.add_parser("show", help="현재 효력 있는 config 출력")
    p_cfg_show.add_argument("--json", action="store_true")
    p_cfg_show.add_argument(
        "--advanced", action="store_true", help="advanced 섹션도 포함"
    )
    p_cfg_show.set_defaults(func=cmd_config_show)

    p_cfg_get = config_sub.add_parser("get", help="단일 키 조회 (예: cleanup.inbox_stale_days)")
    p_cfg_get.add_argument("path", help="점 표기 키 경로")
    p_cfg_get.set_defaults(func=cmd_config_get)

    p_cfg_set = config_sub.add_parser("set", help="단일 키 설정 + 자동 백업")
    p_cfg_set.add_argument("path", help="점 표기 키 경로")
    p_cfg_set.add_argument("value", help="설정할 값 (bool/int/float/str 자동 파싱)")
    p_cfg_set.add_argument(
        "--force", action="store_true", help="advanced 키 변경 시 경고 우회"
    )
    p_cfg_set.set_defaults(func=cmd_config_set)

    p_cfg_edit = config_sub.add_parser("edit", help="$EDITOR로 config.yaml 직접 편집")
    p_cfg_edit.set_defaults(func=cmd_config_edit)

    p_cfg_reset = config_sub.add_parser(
        "reset", help="전체 또는 단일 키를 default로 복원"
    )
    p_cfg_reset.add_argument(
        "path", nargs="?", default=None, help="단일 키 복원 (생략 시 전체)"
    )
    p_cfg_reset.set_defaults(func=cmd_config_reset)

    p_cfg_validate = config_sub.add_parser("validate", help="현재 config 검증")
    p_cfg_validate.set_defaults(func=cmd_config_validate)

    p_assist = sub.add_parser(
        "assistant-status",
        help="비서 모드용 read-only 진단 묶음 (vault·doctor·inbox·draft·last-daily)",
    )
    p_assist.add_argument(
        "--json", action="store_true", help="JSON 원본 그대로 출력 (slash 명령용)"
    )
    p_assist.set_defaults(func=cmd_assistant_status)

    p_cleanup = sub.add_parser(
        "cleanup",
        help="vault 청소 도우미 (오래된·휴면·빈 자료를 archive로 이동)",
    )
    cleanup_sub = p_cleanup.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_cleanup_scan = cleanup_sub.add_parser(
        "scan", help="청소 후보 read-only 출력 (이동 없음)"
    )
    p_cleanup_scan.add_argument("--json", action="store_true")
    p_cleanup_scan.add_argument("--inbox-days", type=int, default=30)
    p_cleanup_scan.add_argument("--dormant-days", type=int, default=90)
    p_cleanup_scan.add_argument("--resume-days", type=int, default=90)
    p_cleanup_scan.add_argument("--memory-inbox-days", type=int, default=60)
    p_cleanup_scan.add_argument("--report-days", type=int, default=90)
    p_cleanup_scan.set_defaults(func=cmd_cleanup_scan)

    p_cleanup_apply = cleanup_sub.add_parser(
        "apply",
        help="선택된 청소 후보를 archive 폴더로 이동 + 매니페스트 작성 (기본 dry-run)",
    )
    p_cleanup_apply.add_argument(
        "--apply",
        action="store_true",
        help="실제 이동 실행 (생략 시 dry-run)",
    )
    p_cleanup_apply.add_argument(
        "--category",
        help="카테고리 필터 (콤마 구분): inbox_stale,dormant_project,old_resume,"
        "stale_memory_inbox,empty_card,old_daily_report,empty_folder",
    )
    p_cleanup_apply.add_argument("--inbox-days", type=int, default=30)
    p_cleanup_apply.add_argument("--dormant-days", type=int, default=90)
    p_cleanup_apply.add_argument("--resume-days", type=int, default=90)
    p_cleanup_apply.add_argument("--memory-inbox-days", type=int, default=60)
    p_cleanup_apply.add_argument("--report-days", type=int, default=90)
    p_cleanup_apply.set_defaults(func=cmd_cleanup_apply)

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

    p_migrate = sub.add_parser(
        "migrate-folders",
        help="기존 flat MemoryInbox/DailyReports 파일을 {YYYY}/{MM}/ 구조로 이동 (1회성)",
    )
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 이동 없이 의도된 이동 리스트만 출력",
    )
    p_migrate.add_argument(
        "--report-unknown",
        action="store_true",
        help="패턴에 맞지 않아 건너뛴 파일 목록 표시",
    )
    p_migrate.add_argument(
        "--vault",
        default=None,
        help="vault 경로 override (기본: config)",
    )
    p_migrate.set_defaults(func=cmd_migrate_folders)

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
