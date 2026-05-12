"""Recipe generator pipeline — single entry point ``generate()``.

Spec: ``specs/007-me-recipes/spec.md`` FR-002, FR-007, FR-011, FR-012, FR-014
Data-model: ``specs/007-me-recipes/data-model.md`` §3 construction order
Research: ``specs/007-me-recipes/research.md`` R-1 (timeout), R-5 (filename), R-6 (last_answer)

Construction order:
    inputs validate → profile → locale → RAG → domain → render system & user prompt
    → invoke LLM (or dry-run) → save markdown → record last_answer → return result.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.endpoints.postprocess import strip_meta_prefix
from synapse_memory.llm.ai_api import complete as ai_api_complete
from synapse_memory.recipes.domain import resolve_domain
from synapse_memory.recipes.loader import SYSTEM_PROMPT_BYTE_CAP
from synapse_memory.recipes.locale import resolve_locale
from synapse_memory.recipes.recipe import (
    GenerationContext,
    GenerationRecipe,
    GenerationResult,
)
from synapse_memory.recipes.registry import RecipeRegistry
from synapse_memory.storage.last_response import (
    AnswerCitation,
    LastAnswerReference,
    new_answer_reference,
    save_last_answer,
)

_PROFILE_FILES = ("Profile.md", "DecisionPatterns.md", "DecisionQualityRegistry.md")
_BUILTIN_DIR_DEFAULT = Path(__file__).resolve().parent / "builtin"
_FILENAME_UNSAFE_RE = re.compile(r"[\\/\x00\r\n]")


class InputValidationError(ValueError):
    """Recipe ``input_schema`` 의 required key 가 inputs 에 없을 때 발생."""


class RecipePromptTooLargeError(ValueError):
    """Rendered system prompt 가 32KB cap 을 초과할 때 발생 (사용자 입력 폭주 방지)."""


def _load_profile_text(vault: Path) -> str:
    parts: list[str] = []
    base = vault / "90_System" / "AI"
    for fname in _PROFILE_FILES:
        p = base / fname
        if p.is_file():
            try:
                parts.append(f"--- {fname} ---\n{p.read_text(encoding='utf-8')[:5000]}")
            except OSError:
                continue
    return "\n\n".join(parts)


def _safe_filename_component(value: str, *, max_len: int = 80) -> str:
    cleaned = _FILENAME_UNSAFE_RE.sub("-", value).strip().strip(".")
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_len].rstrip().rstrip(".")


def _primary_input_value(
    recipe: GenerationRecipe, inputs: dict[str, str]
) -> str:
    for key in recipe.input_schema:  # insertion order preserved
        if recipe.input_schema[key] == "required" and inputs.get(key):
            return inputs[key]
    for key, val in inputs.items():
        if val:
            return val
    return "untitled"


def _render_system_prompt(
    recipe: GenerationRecipe,
    *,
    locale: str,
    domain: str,
    today: datetime.date,
    inputs: dict[str, str],
) -> str:
    """recipe.system_prompt 에 placeholder 치환. 미선언 키는 빈 문자열로 채움."""
    values: dict[str, str] = defaultdict(str)
    values["locale"] = locale
    values["domain"] = domain
    values["today"] = today.isoformat()
    for k, v in inputs.items():
        values[k] = v
    rendered = recipe.system_prompt.format_map(values)
    if len(rendered.encode("utf-8")) > SYSTEM_PROMPT_BYTE_CAP:
        raise RecipePromptTooLargeError(
            f"recipe '{recipe.name}' rendered system_prompt exceeds 32KB"
        )
    return rendered


def _compose_user_prompt(
    *,
    recipe: GenerationRecipe,
    inputs: dict[str, str],
    profile_text: str,
    matched: list[tuple[Any, float]],
) -> str:
    sections: list[str] = []
    sections.append(
        "# 입력\n"
        + "\n".join(f"- {k}: {v}" for k, v in inputs.items() if v)
    )
    if profile_text:
        sections.append("# 사용자 Profile (voice/강점/지향)\n" + profile_text)
    if matched:
        card_blocks: list[str] = []
        for rec, dist in matched:
            cid = rec.metadata.get("card_id") or getattr(rec, "id", "")
            doc = getattr(rec, "document", "")
            card_blocks.append(
                f"---\n[{cid}] (거리={dist:.3f})\n{doc[:1500]}"
            )
        sections.append(
            f"# 관련 자료 ({len(matched)}개, 가까운 순)\n" + "\n\n".join(card_blocks)
        )
    sections.append(
        f"# 지시\n위 자료로 '{recipe.name}' recipe 가 요구하는 결과물을 작성하세요."
    )
    return "\n\n".join(sections)


def _save_markdown(
    *,
    recipe: GenerationRecipe,
    inputs: dict[str, str],
    answer: str,
    vault: Path,
    today: datetime.date,
) -> Path | None:
    if not recipe.save_subpath:
        return None
    save_dir = vault / recipe.save_subpath
    save_dir.mkdir(parents=True, exist_ok=True)
    primary = _safe_filename_component(_primary_input_value(recipe, inputs))
    base = f"{recipe.name} - {primary} ({today.isoformat()})"
    path = save_dir / f"{base}.md"
    if path.exists():
        # R-5 collision fallback: 분 단위 suffix
        ts = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        path = save_dir / f"{recipe.name} - {primary} ({ts}).md"
    path.write_text(answer, encoding="utf-8")
    return path


def _build_last_answer(
    *,
    recipe: GenerationRecipe,
    inputs: dict[str, str],
    matched: list[tuple[Any, float]],
) -> LastAnswerReference:
    citations: list[AnswerCitation] = []
    for rec, _dist in matched:
        cid = rec.metadata.get("card_id") or getattr(rec, "id", None)
        if not cid:
            continue
        citations.append(
            AnswerCitation(
                target_kind="card",
                target_ref=str(cid),
                source_kind=str(rec.metadata.get("source_kind", "")),
                display_name=str(rec.metadata.get("display_name", cid)),
            )
        )
    query = " ".join(v for v in inputs.values() if v) or recipe.name
    return new_answer_reference(
        command=f"me.generate.{recipe.name}",
        query=query,
        citations=tuple(citations),
    )


def _make_registry(vault: Path, builtin_dir: Path) -> RecipeRegistry:
    user_dir = vault / "90_System" / "AI" / "recipes"
    reg = RecipeRegistry(builtin_dir=builtin_dir, user_dir=user_dir)
    reg.scan()
    return reg


def _validate_inputs(recipe: GenerationRecipe, inputs: dict[str, str]) -> None:
    missing = [k for k in recipe.required_inputs if not inputs.get(k)]
    if missing:
        raise InputValidationError(
            f"recipe '{recipe.name}' missing required input(s): {', '.join(missing)}"
        )


def generate(
    recipe_name: str,
    *,
    inputs: dict[str, str] | None = None,
    vault_path: Path | None = None,
    store: Any = None,
    builtin_dir: Path | None = None,
    today: datetime.date | None = None,
    cli_language: str | None = None,
    cli_domain: str | None = None,
    company: Any = None,
    dry_run: bool = False,
    save_last: bool = True,
    ai_env: Any = None,
    model_override: str | None = None,
    timeout_override: int | None = None,
    disable_save: bool = False,
    top_k_override: int | None = None,
    require_matched: bool = False,
) -> GenerationResult:
    """Recipe 1 회 실행 — orchestrator entry point.

    Construction order: input validation → profile → locale → RAG → domain →
    render → invoke (or skip on dry_run) → save → record last_answer → return.
    """
    inputs = dict(inputs or {})
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    builtin = builtin_dir or _BUILTIN_DIR_DEFAULT
    today_resolved = today or datetime.date.today()

    registry = _make_registry(vault, builtin)
    recipe = registry.get(recipe_name)

    _validate_inputs(recipe, inputs)

    # inputs 에 company_id 가 있으면 CompanyCard 자동 로드 — locale precedence 1 순위.
    if company is None and inputs.get("company_id"):
        try:
            from synapse_memory.cards.company import load_company_card

            company = load_company_card(inputs["company_id"], vault_path=vault)
        except (FileNotFoundError, ValueError):
            company = None  # 미존재 시 fallback

    profile_text = _load_profile_text(vault) if recipe.use_profile else ""
    profile_used = bool(profile_text)

    locale, locale_src = (
        resolve_locale(cli_arg=cli_language, company=company, profile_text=profile_text)
        if recipe.locale_aware
        else ("한국어", "default")
    )

    matched: list[tuple[Any, float]] = []
    if store is not None:
        rag_top_k = top_k_override or recipe.rag_top_k
        try:
            matched = list(
                store.query(
                    None,
                    top_k=rag_top_k,
                    where=recipe.rag_filter,
                )
            )
        except TypeError:
            # store.query signature variation tolerance (for stubs / future stores)
            matched = list(store.query())

    if require_matched and not matched:
        raise ValueError(
            f"recipe '{recipe.name}' requires RAG matches but got 0. "
            "`synapse-memory rag index` 먼저 실행하세요."
        )

    domain, domain_src = (
        resolve_domain(
            cli_arg=cli_domain,
            profile_text=profile_text,
            matched=matched,
        )
        if recipe.domain_aware or cli_domain
        else ("generic", "default")
    )

    system_rendered = _render_system_prompt(
        recipe,
        locale=locale,
        domain=domain,
        today=today_resolved,
        inputs=inputs,
    )
    user_prompt = _compose_user_prompt(
        recipe=recipe,
        inputs=inputs,
        profile_text=profile_text,
        matched=matched,
    )

    ctx = GenerationContext(
        recipe=recipe,
        inputs=inputs,
        profile_text=profile_text,
        profile_used=profile_used,
        locale=locale,
        locale_source=locale_src,
        domain=domain,
        domain_source=domain_src,
        rag_mode=recipe.rag_mode,
        matched_records=matched,
        today=today_resolved,
        rendered_system_prompt=system_rendered,
        rendered_user_prompt=user_prompt,
    )

    if dry_run:
        preview = (
            f"# DRY-RUN PREVIEW for recipe '{recipe.name}'\n\n"
            f"## system prompt\n```\n{system_rendered}\n```\n\n"
            f"## user prompt\n```\n{user_prompt}\n```"
        )
        return GenerationResult(
            recipe_name=recipe.name,
            answer_markdown=preview,
            saved_path=None,
            source_ids=[
                str(rec.metadata.get("card_id") or getattr(rec, "id", ""))
                for rec, _ in matched
                if rec.metadata.get("card_id") or getattr(rec, "id", None)
            ],
            profile_used=ctx.profile_used,
            locale=locale,
            locale_source=locale_src,
            domain=domain,
            domain_source=domain_src,
            rag_mode=recipe.rag_mode,
        )

    answer = ai_api_complete(
        user_prompt,
        system=system_rendered,
        model=model_override or recipe.model,
        timeout=timeout_override or recipe.timeout,
        env=ai_env,
    )
    answer = strip_meta_prefix(answer)

    saved_path = (
        None
        if disable_save
        else _save_markdown(
            recipe=recipe,
            inputs=inputs,
            answer=answer,
            vault=vault,
            today=today_resolved,
        )
    )

    last_ref: LastAnswerReference | None = None
    if save_last:
        ref = _build_last_answer(recipe=recipe, inputs=inputs, matched=matched)
        try:
            save_last_answer(ref)
        except (OSError, ValueError):
            pass  # best-effort — last_answer 실패는 generate 실패로 보지 않음
        last_ref = ref

    source_ids = [c.target_ref for c in (last_ref.citations if last_ref else ())]

    return GenerationResult(
        recipe_name=recipe.name,
        answer_markdown=answer,
        saved_path=saved_path,
        source_ids=source_ids,
        profile_used=profile_used,
        locale=locale,
        locale_source=locale_src,
        domain=domain,
        domain_source=domain_src,
        rag_mode=recipe.rag_mode,
        last_answer_ref=last_ref,
    )
