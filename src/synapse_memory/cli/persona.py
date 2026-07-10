"""persona and recall commands."""

from __future__ import annotations

import argparse
import datetime
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from synapse_memory.cli.common import FAIL, OK, api


def cmd_me_what_did_i_think(args: argparse.Namespace) -> int:
    args.top_k = api()._arg_or_config(args.top_k, "top_k.recall", 8)
    args.model = api()._resolve_model(args.model, "recall")
    api()._enforce_cost_cap("persona what-did-i-think")
    api()._interactive_guard("persona what-did-i-think", "recall")

    timeline_flag = bool(getattr(args, "timeline", False))
    hybrid_flag = bool(getattr(args, "hybrid", False))
    by_arg = getattr(args, "by", None)
    if hybrid_flag and (timeline_flag or by_arg == "time"):
        print("error: --timeline and --hybrid conflict — pick one.", file=sys.stderr)
        return 1
    if timeline_flag and by_arg == "distance":
        print("error: --timeline and --by distance conflict — pick one.", file=sys.stderr)
        return 1
    if timeline_flag or by_arg == "time":
        effective_by = "time"
    elif by_arg == "distance":
        effective_by = "distance"
    else:
        effective_by = "distance"

    limit = int(getattr(args, "limit", 20))
    if not (1 <= limit <= 100):
        print(f"error: --limit must be in [1, 100], got {limit}", file=sys.stderr)
        return 2

    ai_env = None
    if effective_by == "distance":
        ai_env = api().detect_ai_environment(model=args.model)
        if not ai_env.ready:
            print(f"{FAIL} AI provider 사용 불가", file=sys.stderr)
            return 2
    try:
        result = api().what_did_i_think(
            args.topic,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
            by=effective_by,
            limit=limit,
            hybrid=hybrid_flag,
        )
    except (api().AIError, ValueError) as exc:
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
    args.top_k = api()._arg_or_config(args.top_k, "top_k.decide", 6)
    args.model = api()._resolve_model(args.model, "decide")
    api()._enforce_cost_cap("persona decide")
    api()._interactive_guard("persona decide", "decide")
    ai_env = api().detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가", file=sys.stderr)
        return 2
    try:
        result = api().decide(
            args.situation,
            top_k=args.top_k,
            model=args.model,
            ai_env=ai_env,
        )
    except (api().AIError, ValueError) as exc:
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


def cmd_me_update_profile(args: argparse.Namespace) -> int:
    args.sample_lines = api()._arg_or_config(args.sample_lines, "profile.sample_lines", 200)
    args.model = api()._resolve_model(args.model, "update_profile")
    api()._enforce_cost_cap("persona update-profile")
    api()._interactive_guard("persona update-profile", "update-profile")
    ai_env = api().detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}", file=sys.stderr)
        return 2

    try:
        print(f"ProfileFact 추출 중 (sample={args.sample_lines})...")
        facts = api().extract_profile_facts(
            sample_lines=args.sample_lines,
            model=args.model,
            ai_env=ai_env,
        )
        print(f"  → {len(facts)} fact 추출")

        patterns = []
        if not args.facts_only:
            print("DecisionPattern 추출 중...")
            patterns = api().extract_decision_patterns(
                sample_lines=args.sample_lines,
                model=args.model,
                ai_env=ai_env,
            )
            print(f"  → {len(patterns)} pattern 추출")
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except api().AIError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    path = api().save_profile_update(facts, patterns)
    print(f"\n{OK} wiki profile 저장: {path}")
    return 0


def cmd_persona_ingest(args: argparse.Namespace) -> int:
    args.model = api()._resolve_model(args.model, "update_profile")
    api()._enforce_cost_cap("persona ingest")
    api()._interactive_guard("persona ingest", "update-profile")

    paths = [Path(path) for path in args.file]
    try:
        result = api().ingest_files(paths)
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2

    for file_result in result.files:
        if file_result.skipped_reason == "unsupported":
            ext_list = ", ".join(sorted(api().SUPPORTED_EXTENSIONS))
            print(
                f"  SKIPPED (unsupported): {file_result.source_path.name} "
                f"(지원: {ext_list})",
                file=sys.stderr,
            )
        elif file_result.skipped_reason == "empty":
            print(
                f"  SKIPPED (빈 파일): {file_result.source_path.name} — raw 는 L0 에 보존됨",
                file=sys.stderr,
            )

    if not result.combined_text:
        print(f"{FAIL} 흡수 가능한 텍스트 없음", file=sys.stderr)
        return 1

    print(f"INGESTED: {result.accepted_count} files mirrored to L0 private storage")
    ai_env = api().detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}", file=sys.stderr)
        return 2

    try:
        print("ProfileFact 추출 중 (외부 자료 기반)...")
        facts = api().extract_profile_facts(
            sample_lines=0,
            model=args.model,
            ai_env=ai_env,
            extra_text=result.combined_text,
        )
        print(f"  → {len(facts)} fact 추출")
    except api().AIError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    path = api().save_profile_update(facts, patterns=None)
    print(f"\n{OK} wiki profile 저장: {path}")
    return 0


def cmd_persona_design_project(args: argparse.Namespace) -> int:
    args.top_k = api()._arg_or_config(args.top_k, "top_k.resume", 6)
    args.model = api()._resolve_model(args.model, "generate")
    api()._enforce_cost_cap("persona design-project")
    api()._interactive_guard("persona design-project", "decide")
    ai_env = api().detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}", file=sys.stderr)
        return 2

    from synapse_memory.recipes import (
        InputValidationError,
        RecipeNotFoundError,
        RecipeValidationError,
        generate as recipes_generate,
    )

    try:
        result = recipes_generate(
            "design_project",
            inputs={"idea": args.idea},
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
    except api().AIError as exc:
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
    args.top_k = api()._arg_or_config(args.top_k, "top_k.resume", 6)
    args.model = api()._resolve_model(args.model, "resume")
    api()._enforce_cost_cap("persona draft-resume")
    api()._interactive_guard("persona draft-resume", "resume")
    ai_env = api().detect_ai_environment(model=args.model)
    if not ai_env.ready:
        print(f"{FAIL} AI provider 사용 불가:", file=sys.stderr)
        for reason in ai_env.reasons_unavailable():
            print(f"  - {reason}", file=sys.stderr)
        return 2

    try:
        result = api().draft_resume(
            args.company_id,
            top_k_projects=args.top_k,
            model=args.model,
            ai_env=ai_env,
        )
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except (api().AIError, ValueError) as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    print(f"{OK} 이력서 생성: {result.saved_path}")
    print(f"  매칭 ProjectCard ({len(result.project_card_ids)}):")
    for pid in result.project_card_ids:
        print(f"    - {pid}")
    return 0


def _parse_input_kv(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in items or []:
        if "=" not in raw:
            raise ValueError(f"--input must be key=value, got '{raw}'")
        key, _, value = raw.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"--input key empty: '{raw}'")
        out[key] = value
    return out


def cmd_me_generate(args: argparse.Namespace) -> int:
    api()._enforce_cost_cap(f"persona generate {args.recipe}")
    from synapse_memory.recipes import (
        InputValidationError,
        RecipeNotFoundError,
        RecipePromptTooLargeError,
        RecipeValidationError,
        generate as recipes_generate,
    )

    api()._interactive_guard(f"persona generate {args.recipe}", f"generate-{args.recipe}")
    try:
        inputs = _parse_input_kv(args.input or [])
    except ValueError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    vault_path = Path(args.vault).expanduser().resolve() if args.vault else None
    try:
        today_resolved = datetime.date.fromisoformat(args.today) if args.today else None
    except ValueError as exc:
        print(f"{FAIL} --today must be YYYY-MM-DD: {exc}", file=sys.stderr)
        return 1

    t0 = time.monotonic()
    try:
        result = recipes_generate(
            args.recipe,
            inputs=inputs,
            vault_path=vault_path,
            today=today_resolved,
            cli_language=args.language,
            cli_domain=args.domain,
            rag_mode_override=args.rag_mode,
            dry_run=args.dry_run,
            model_override=args.model,
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
    except api().AIError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 10

    duration_ms = int((time.monotonic() - t0) * 1000)
    sys.stdout.write(result.answer_markdown.rstrip() + "\n")
    if result.saved_path:
        sys.stdout.write(f"\n[saved] {result.saved_path}\n")
    sys.stdout.flush()
    recipe_source = "?"
    try:
        from synapse_memory.config import get_config
        from synapse_memory.recipes.registry import RecipeRegistry

        vault = vault_path or api()._resolve_vault()
        registry = RecipeRegistry(
            builtin_dir=Path(__file__).resolve().parents[1] / "recipes" / "builtin",
            user_dir=vault / get_config().vault_folders.system.ai.recipes,
        )
        registry.scan()
        recipe = registry.recipes.get(result.recipe_name)
        recipe_source = recipe.source if recipe is not None else "?"
    except Exception:
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
    from synapse_memory.config import get_config
    from synapse_memory.recipes.registry import RecipeRegistry

    vault = api()._resolve_vault(argparse.Namespace(vault=vault_arg))
    registry = RecipeRegistry(
        builtin_dir=Path(__file__).resolve().parents[1] / "recipes" / "builtin",
        user_dir=vault / get_config().vault_folders.system.ai.recipes,
    )
    registry.scan()
    return registry


def _format_recipes_table(recipes: list[Any]) -> str:
    headers = ("NAME", "SOURCE", "REQUIRED INPUTS", "DESCRIPTION")
    rows: list[tuple[str, str, str, str]] = [headers]
    for recipe in recipes:
        rows.append(
            (
                recipe.name,
                recipe.source,
                ",".join(recipe.required_inputs) or "-",
                recipe.description,
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = ["  ".join(col.ljust(widths[j]) for j, col in enumerate(row)) for row in rows]
    return "\n".join(lines) + "\n"


def _recipes_envelope(
    ok: bool,
    data: object,
    errors: Iterable[object] | None = None,
) -> str:
    import json

    payload = {"ok": ok, "data": data, "errors": list(errors or [])}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def cmd_me_recipes_list(args: argparse.Namespace) -> int:
    try:
        registry = _recipes_registry_for_vault(args.vault)
    except Exception as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    source_filter = getattr(args, "source", "all")
    items = [
        recipe
        for recipe in registry.list()
        if source_filter == "all" or recipe.source == source_filter
    ]
    if getattr(args, "json", False):
        data = [
            {
                "name": recipe.name,
                "source": recipe.source,
                "description": recipe.description,
                "required_inputs": list(recipe.required_inputs),
                "optional_inputs": list(recipe.optional_inputs),
                "save_subpath": recipe.save_subpath,
                "locale_aware": recipe.locale_aware,
                "domain_aware": recipe.domain_aware,
            }
            for recipe in items
        ]
        sys.stdout.write(_recipes_envelope(True, data))
        return 0

    sys.stdout.write(_format_recipes_table(items))
    if getattr(args, "verbose", False) and registry.skipped:
        sys.stdout.write("\n# Skipped\n")
        for path, reason in registry.skipped:
            sys.stdout.write(f"- {path}: {reason}\n")
    return 0


def cmd_me_recipes_show(args: argparse.Namespace) -> int:
    from synapse_memory.recipes.registry import RecipeNotFoundError

    try:
        registry = _recipes_registry_for_vault(args.vault)
    except Exception as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1

    try:
        recipe = registry.get(args.recipe)
    except RecipeNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        if exc.suggestions:
            print("  가까운 후보: " + ", ".join(exc.suggestions), file=sys.stderr)
        return 2

    prompt_lines = recipe.system_prompt.splitlines()
    show_full = getattr(args, "full", False)
    shown_prompt = prompt_lines if show_full else prompt_lines[:20]
    if getattr(args, "json", False):
        data = {
            "name": recipe.name,
            "source": recipe.source,
            "source_path": str(recipe.source_path),
            "description": recipe.description,
            "required_inputs": list(recipe.required_inputs),
            "optional_inputs": list(recipe.optional_inputs),
            "rag_filter": recipe.rag_filter,
            "rag_top_k": recipe.rag_top_k,
            "save_subpath": recipe.save_subpath,
            "use_profile": recipe.use_profile,
            "locale_aware": recipe.locale_aware,
            "domain_aware": recipe.domain_aware,
            "timeout": recipe.timeout,
            "model": recipe.model,
            "system_prompt": "\n".join(shown_prompt),
        }
        sys.stdout.write(_recipes_envelope(True, data))
        return 0

    sys.stdout.write(f"name:           {recipe.name}\n")
    sys.stdout.write(f"source:         {recipe.source}\n")
    sys.stdout.write(f"source_path:    {recipe.source_path}\n")
    sys.stdout.write(f"description:    {recipe.description}\n")
    sys.stdout.write("input_schema:\n")
    for key, required in recipe.input_schema.items():
        sys.stdout.write(f"  - {key} ({required})\n")
    sys.stdout.write(f"rag_filter:     {recipe.rag_filter}\n")
    sys.stdout.write(f"rag_top_k:      {recipe.rag_top_k}\n")
    sys.stdout.write(f"use_profile:    {recipe.use_profile}\n")
    sys.stdout.write(f"save_subpath:   {recipe.save_subpath}\n")
    sys.stdout.write(f"locale_aware:   {recipe.locale_aware}\n")
    sys.stdout.write(f"domain_aware:   {recipe.domain_aware}\n")
    sys.stdout.write(f"timeout:        {recipe.timeout}\n")
    sys.stdout.write(f"model:          {recipe.model}\n\n")
    suffix = " (full):" if show_full else " (first 20 lines):"
    sys.stdout.write(f"system_prompt{suffix}\n")
    for line in shown_prompt:
        sys.stdout.write(line + "\n")
    return 0


def _add_recall_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", help="회상할 주제")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeline", action="store_true")
    parser.add_argument("--by", choices=("time", "distance"), default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="호환 플래그: provider-only에서는 ranking 차이 없음",
    )
    parser.set_defaults(func=cmd_me_what_did_i_think)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    recall = subparsers.add_parser(
        "recall",
        help="주제에 대한 과거 사고 회상",
        description="persona what-did-i-think의 top-level alias입니다.",
    )
    _add_recall_args(recall)

    persona = subparsers.add_parser("persona", help="Persona 통합 endpoints (이전 'me')")
    persona_sub = persona.add_subparsers(dest="action", required=True, metavar="ACTION")

    resume = persona_sub.add_parser("draft-resume", help="회사 맞춤 이력서 자동 작성")
    resume.add_argument("company_id")
    resume.add_argument("--top-k", type=int, default=None)
    resume.add_argument("--model", default=None)
    resume.set_defaults(func=cmd_me_draft_resume)

    update = persona_sub.add_parser("update-profile", help="raw → ProfileFact/DecisionPattern")
    update.add_argument("--sample-lines", type=int, default=None)
    update.add_argument("--model", default=None)
    update.add_argument("--facts-only", action="store_true")
    update.set_defaults(func=cmd_me_update_profile)

    ingest = persona_sub.add_parser("ingest", help="외부 markdown/txt 흡수")
    ingest.add_argument("--file", action="append", required=True, metavar="PATH")
    ingest.add_argument("--model", default=None)
    ingest.set_defaults(func=cmd_persona_ingest)

    design = persona_sub.add_parser("design-project", help="새 프로젝트 설계 초안")
    design.add_argument("idea")
    design.add_argument("--top-k", type=int, default=None)
    design.add_argument("--model", default=None)
    design.set_defaults(func=cmd_persona_design_project)

    thought = persona_sub.add_parser("what-did-i-think", help="주제에 대한 과거 사고 회상")
    _add_recall_args(thought)

    decide = persona_sub.add_parser("decide", help="의사결정 코파일럿")
    decide.add_argument("situation")
    decide.add_argument("--top-k", type=int, default=None)
    decide.add_argument("--model", default=None)
    decide.set_defaults(func=cmd_me_decide)

    generate = persona_sub.add_parser("generate", help="recipe 기반 결과물 생성")
    generate.add_argument("recipe")
    generate.add_argument("--input", action="append", default=[], metavar="KEY=VALUE")
    generate.add_argument("--language", default=None)
    generate.add_argument("--domain", default=None)
    generate.add_argument("--rag-mode", choices=("dense", "hybrid"), default=None)
    generate.add_argument("--model", default=None)
    generate.add_argument("--vault", default=None)
    generate.add_argument("--today", default=None)
    generate.add_argument("--dry-run", action="store_true")
    generate.set_defaults(func=cmd_me_generate)

    recipes = persona_sub.add_parser("recipes", help="recipe 목록·상세")
    recipes_sub = recipes.add_subparsers(
        dest="recipes_action",
        required=True,
        metavar="RECIPES_ACTION",
    )
    recipe_list = recipes_sub.add_parser("list", help="모든 recipe 표 출력")
    recipe_list.add_argument("--source", choices=("builtin", "user", "all"), default="all")
    recipe_list.add_argument("--vault", default=None)
    recipe_list.add_argument("--verbose", action="store_true")
    recipe_list.add_argument("--json", action="store_true")
    recipe_list.set_defaults(func=cmd_me_recipes_list)

    recipe_show = recipes_sub.add_parser("show", help="recipe 1 건 상세")
    recipe_show.add_argument("recipe")
    recipe_show.add_argument("--vault", default=None)
    recipe_show.add_argument("--json", action="store_true")
    recipe_show.add_argument("--full", action="store_true")
    recipe_show.set_defaults(func=cmd_me_recipes_show)
