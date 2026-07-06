"""Recipe generator pipeline — single entry point ``generate()``.

Spec: ``specs/007-persona-recipes/spec.md`` FR-002, FR-007, FR-011, FR-012, FR-014
Data-model: ``specs/007-persona-recipes/data-model.md`` §3 construction order
Research: ``specs/007-persona-recipes/research.md`` R-1 (timeout), R-5 (filename), R-6 (last_answer)

Construction order:
    inputs validate → profile → locale → related cards → domain → render system & user prompt
    → invoke LLM (or dry-run) → save markdown → record last_answer → return result.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import contextlib
import datetime
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synapse_memory.cards.card_index import CardKind, build_card_index
from synapse_memory.cards.card_text import (
    company_card_to_text,
    insight_card_to_text,
    project_card_to_text,
)
from synapse_memory.config import get_config, get_vault_path
from synapse_memory.endpoints.postprocess import strip_meta_prefix
from synapse_memory.llm.ai_api import complete as ai_api_complete
from synapse_memory.recipes.domain import resolve_domain
from synapse_memory.recipes.loader import SYSTEM_PROMPT_BYTE_CAP
from synapse_memory.recipes.locale import resolve_locale
from synapse_memory.recipes.recipe import (
    GenerationContext,
    GenerationRecipe,
    GenerationResult,
    RecipeRagMode,
)
from synapse_memory.recipes.registry import RecipeRegistry
from synapse_memory.storage.last_response import (
    AnswerCitation,
    LastAnswerReference,
    new_answer_reference,
    save_last_answer,
)
from synapse_memory.wiki.llm_retrieval import select_related

_PROFILE_FILES = ("Profile.md", "DecisionPatterns.md")
_BUILTIN_DIR_DEFAULT = Path(__file__).resolve().parent / "builtin"
_FILENAME_UNSAFE_RE = re.compile(r"[\\/\x00\r\n]")


class InputValidationError(ValueError):
    """Recipe ``input_schema`` 의 required key 가 inputs 에 없을 때 발생."""


class RecipePromptTooLargeError(ValueError):
    """Rendered system prompt 가 32KB cap 을 초과할 때 발생 (사용자 입력 폭주 방지)."""


@dataclass(frozen=True)
class _CardMatch:
    """provider 선별된 카드 1건 — 이전 VectorRecord 인터페이스 호환 shape.

    ``metadata``(card_id/source_kind/display_name 등)·``document``(full text)·``id``를
    노출해 ``_compose_user_prompt``/``_build_last_answer``/domain 추출이 기존 코드 그대로
    동작한다. 거리(score)는 provider 선별이라 의미 없어 항상 0.0으로 동반된다.
    """

    id: str
    document: str
    metadata: dict[str, str] = field(default_factory=dict)


# rag_filter.source_kind (예 "card_project") → CardIndex kind ("project")
_SOURCE_KIND_TO_CARD_KIND: dict[str, CardKind] = {
    "card_project": "project",
    "card_company": "company",
    "card_insight": "insight",
}


def _load_profile_text(vault: Path) -> str:
    """vault Profile/DecisionPatterns 전체 로드.

    이전: 파일당 5000자 silent truncation 으로 사용자가 알아챌 수 없는 손실 발생.
    이후 (B2, eng-review 2026-05-13): 전체 로드. 시스템 prompt 32KB cap 이 자동
    안전망 — Profile 이 너무 크면 ``RecipePromptTooLargeError`` 로 명시적 실패 (silent X).
    """
    parts: list[str] = []
    base = vault / get_config().vault_folders.system.ai.root
    for fname in _PROFILE_FILES:
        p = base / fname
        if p.is_file():
            try:
                parts.append(f"--- {fname} ---\n{p.read_text(encoding='utf-8')}")
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
    for _key, val in inputs.items():
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
        command=f"persona.generate.{recipe.name}",
        query=query,
        citations=tuple(citations),
    )


def _make_registry(vault: Path, builtin_dir: Path) -> RecipeRegistry:
    user_dir = vault / get_config().vault_folders.system.ai.recipes
    reg = RecipeRegistry(builtin_dir=builtin_dir, user_dir=user_dir)
    reg.scan()
    return reg


def _validate_inputs(recipe: GenerationRecipe, inputs: dict[str, str]) -> None:
    missing = [k for k in recipe.required_inputs if not inputs.get(k)]
    if missing:
        raise InputValidationError(
            f"recipe '{recipe.name}' missing required input(s): {', '.join(missing)}"
        )


def _build_rag_query(recipe: GenerationRecipe, inputs: dict[str, str]) -> str:
    parts = [recipe.name, recipe.description]
    parts.extend(f"{key}: {value}" for key, value in inputs.items() if value)
    return "\n".join(parts)


def _resolve_rag_mode(
    *,
    recipe: GenerationRecipe,
    override: RecipeRagMode | None,
) -> RecipeRagMode:
    return override or recipe.rag_mode


def _kinds_for_recipe(recipe: GenerationRecipe) -> tuple[CardKind, ...]:
    """recipe.rag_filter.source_kind → CardIndex kinds 제한. 미지정이면 전체."""
    rag_filter = recipe.rag_filter or {}
    source_kind = rag_filter.get("source_kind")
    if source_kind and source_kind in _SOURCE_KIND_TO_CARD_KIND:
        return (_SOURCE_KIND_TO_CARD_KIND[source_kind],)
    return ("project", "company", "insight")


def _load_card_match(
    *, card_id: str, kind: CardKind, vault: Path, created: str = ""
) -> _CardMatch | None:
    """선별된 card_id의 full text를 로드해 _CardMatch로 변환. 실패 시 None."""
    from synapse_memory.cards.company import load_company_card
    from synapse_memory.cards.insight import load_insight_card
    from synapse_memory.cards.project import load_project_card

    try:
        if kind == "project":
            card = load_project_card(card_id, vault_path=vault)
            return _CardMatch(
                id=card_id,
                document=project_card_to_text(card),
                metadata={
                    "card_id": card.project_id,
                    "source_kind": "card_project",
                    "display_name": card.display_name,
                    "status": card.status,
                    "period_end": card.period_end or "",
                    "created": card.created or "",
                    "last_reviewed": card.last_reviewed or "",
                },
            )
        if kind == "company":
            company = load_company_card(card_id, vault_path=vault)
            return _CardMatch(
                id=card_id,
                document=company_card_to_text(company),
                metadata={
                    "card_id": company.company_id,
                    "source_kind": "card_company",
                    "display_name": company.display_name,
                    "status": company.status,
                    "created": company.created or "",
                    "last_reviewed": company.last_reviewed or "",
                },
            )
        if not created:
            return None
        insight = load_insight_card(card_id, created, vault_path=vault)
        return _CardMatch(
            id=card_id,
            document=insight_card_to_text(insight),
            metadata={
                "card_id": insight.insight_id,
                "source_kind": "card_insight",
                "display_name": insight.question,
                "created": insight.created or "",
            },
        )
    except (FileNotFoundError, ValueError, OSError):
        return None


def _retrieve_matches(
    *,
    recipe: GenerationRecipe,
    inputs: dict[str, str],
    vault: Path,
    store: Any,
    top_k_override: int | None,
) -> list[tuple[Any, float]]:
    """provider 선별로 관련 카드 매칭 (로컬 임베딩 제거, 020).

    ``store``가 명시적으로 주입되면 기존 테스트/호환 adapter로 취급해 provider 호출
    없이 deterministic query 결과를 사용한다. 기본 production path는 CardIndex +
    provider 선별이다.

    CardIndex 구성 → ``select_related`` 로 card_id 선별 → 선택 카드 full text 로드 →
    ``list[tuple[_CardMatch, 0.0]]`` 반환(거리 의미 없음). 빈 인덱스/선별 0건 → [].
    """
    rag_top_k = top_k_override or recipe.rag_top_k
    rag_query = _build_rag_query(recipe, inputs)
    rag_filter = dict(recipe.rag_filter) if recipe.rag_filter is not None else None

    if store is not None:
        try:
            return list(store.query(rag_query, top_k=rag_top_k, where=rag_filter))
        except TypeError:
            return list(store.query())

    kinds = _kinds_for_recipe(recipe)

    index = build_card_index(vault_path=vault, kinds=kinds)
    if not index.entries:
        return []

    selected = select_related(rag_query, index, max_pages=rag_top_k)
    if not selected:
        return []

    by_id = index.by_id()
    matches: list[tuple[Any, float]] = []
    for card_id in selected:
        entry = by_id.get(card_id)
        if entry is None:
            continue
        match = _load_card_match(
            card_id=card_id,
            kind=entry.kind,
            vault=vault,
            created=entry.meta.get("created", ""),
        )
        if match is not None:
            matches.append((match, 0.0))
    return matches


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
    rag_mode_override: RecipeRagMode | None = None,
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
    rag_mode = _resolve_rag_mode(recipe=recipe, override=rag_mode_override)

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

    matched = _retrieve_matches(
        recipe=recipe,
        inputs=inputs,
        vault=vault,
        store=store,
        top_k_override=top_k_override,
    )

    if require_matched and not matched:
        raise ValueError(
            f"recipe '{recipe.name}' requires RAG matches but got 0. "
            "vault에 관련 Card를 먼저 생성하세요 (`synapse-memory daily`)."
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
        rag_mode=rag_mode,
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
            rag_mode=rag_mode,
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
        with contextlib.suppress(OSError, ValueError):
            save_last_answer(ref)
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
        rag_mode=rag_mode,
        last_answer_ref=last_ref,
    )
