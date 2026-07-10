"""me endpoints — 사용자 voice/data로 결과 생성하는 클론 모드.

- draft_resume      : 회사 맞춤 이력서
- what_did_i_think  : 주제 회상 (세컨드 브레인, 시간순)
- decide            : 의사결정 코파일럿 (Profile + DecisionPatterns + RAG)

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import contextlib
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from synapse_memory.config import get_config, get_vault_path
from synapse_memory.feedback.last_response import (
    AnswerCitation,
    new_answer_reference,
    save_last_answer,
)
from synapse_memory.llm.ai_api import AIEnvironment, resolve_model_for_task
from synapse_memory.model import Entity
from synapse_memory.recall.timeline import (
    _EMPTY_MESSAGE,
    _format_timeline_output,
    _group_by_quarter,
    _resolve_sort_ts,
    _sort_by_time,
)
from synapse_memory.recipes.pipeline import build_entity_index, entity_to_text
from synapse_memory.store import load_entity

DEFAULT_PROJECTS_FOR_RESUME = 6
DEFAULT_RESUME_TIMEOUT = 240
DRAFTS_SUBPATH = Path("30_Creative") / "Drafts"

_RESUME_RECIPE_NAME = "resume"  # 007-persona-recipes — `draft_resume` 는 wrapper


@dataclass
class ResumeDraft:
    company_id: str
    company_name: str
    saved_path: Path
    project_card_ids: list[str] = field(default_factory=list)
    raw_text: str = ""


def _company_search_query(company: Entity) -> str:
    """Company entity에서 매칭 query 문자열 추출."""
    parts: list[str] = [company.display_name]
    for p in company.positions:
        parts.append(p.title)
        if p.seniority:
            parts.append(p.seniority)
        parts.extend(p.keywords)
    if company.notes:
        parts.append(company.notes[:300])
    if company.body:
        parts.append(company.body[:500])
    return " ".join(parts)


def _build_resume_prompt(company: Entity, matched: list[tuple[object, float]]) -> str:
    """Company entity + 매칭 Project entity들로 AI provider prompt 빌드.

    ``matched`` 요소는 ``.metadata``(card_id)·``.document``·``.id``를 노출하는 record
    (provider 선별 _CardMatch 또는 호환 객체). 거리는 provider 선별이라 의미 없음.
    """
    company_block = entity_to_text(company)
    project_blocks: list[str] = []
    for rec, _score in matched:
        meta = getattr(rec, "metadata", {}) or {}
        cid = meta.get("card_id") or getattr(rec, "id", "")
        document = getattr(rec, "document", "")
        project_blocks.append(f"---\n[{cid}]\n{document}")

    return (
        f"# 지원 회사\n{company_block}\n\n"
        f"# 사용자 Project entity ({len(matched)}개)\n"
        + "\n\n".join(project_blocks)
        + "\n\n# 지시\n위 자료로 회사 맞춤 한국어 이력서를 작성하세요. "
        f"오늘 날짜: {datetime.date.today().isoformat()}."
    )


def _task_model(
    model: str | None,
    task: str,
    ai_env: AIEnvironment | None,
) -> str | None:
    return model or resolve_model_for_task(
        task, provider=getattr(ai_env, "provider", None)
    ) or getattr(ai_env, "model", None)


def draft_resume(
    company_id: str,
    *,
    top_k_projects: int = DEFAULT_PROJECTS_FOR_RESUME,
    model: str | None = None,
    vault_path: Path | None = None,
    ai_env: AIEnvironment | None = None,
    store: object | None = None,  # 시그니처 호환 — provider 선별로 미사용
    timeout: int = DEFAULT_RESUME_TIMEOUT,
) -> ResumeDraft:
    """회사 맞춤 이력서 자동 생성 → vault에 저장 (007-persona-recipes wrapper).

    내부적으로 ``recipes.pipeline.generate("resume", ...)`` 를 호출하여
    Profile + locale (Company.resume_language → Profile.preferred_lang →
    default) + domain (Profile.domain → tags → generic) 을 인식한다.

    외부 시그니처와 ``ResumeDraft`` 반환은 SC-005 회귀 가드로 보존.

    Raises:
        FileNotFoundError: Company entity 없음.
        AIError: 호출 실패.
        ValueError: 매칭 Project entity 0건.
    """
    from synapse_memory.recipes import generate as recipes_generate

    company = load_entity("company", company_id, vault_path=vault_path)

    try:
        result = recipes_generate(
            _RESUME_RECIPE_NAME,
            inputs={"company_id": company_id},
            vault_path=vault_path,
            ai_env=ai_env,
            model_override=_task_model(model, "resume", ai_env),
            timeout_override=timeout,
            company=company,
            disable_save=True,  # SC-005: wrapper 가 기존 filename rule 로 직접 저장
            top_k_override=top_k_projects,
            require_matched=True,  # Project entity 0 건 → ValueError
        )
    except ValueError as exc:
        # 기존 message 호환 (SC-005)
        if "got 0" in str(exc):
            raise ValueError(
                "매칭 Project entity 0건 — vault에 Project entity를 먼저 생성하세요"
            ) from exc
        raise

    if not result.source_ids:
        raise ValueError(
            "매칭 Project entity 0건 — vault에 Project entity를 먼저 생성하세요"
        )

    # 기존 filename rule 유지 (SC-005): `Resume - {display_name} ({YYYY-MM}).md`
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    drafts_dir = vault / get_config().vault_folders.creative.drafts
    drafts_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    safe_name = company.display_name.replace("/", "-").replace("\\", "-")
    filename = f"Resume - {safe_name} ({today[:7]}).md"
    path = drafts_dir / filename
    path.write_text(result.answer_markdown, encoding="utf-8")

    return ResumeDraft(
        company_id=company_id,
        company_name=company.display_name,
        saved_path=path,
        project_card_ids=result.source_ids[:top_k_projects],
        raw_text=result.answer_markdown,
    )


# ---------------------------------------------------------------------------
# what_did_i_think — 주제 회상 (세컨드 브레인)
# ---------------------------------------------------------------------------


_RECALL_RECIPE_NAME = "recall"  # 007-persona-recipes — what_did_i_think distance-mode wrapper


@dataclass
class WhatDidIThinkResult:
    topic: str
    answer: str
    source_ids: list[str] = field(default_factory=list)


def what_did_i_think(
    topic: str,
    *,
    top_k: int = 8,
    model: str | None = None,
    ai_env: AIEnvironment | None = None,
    store: object | None = None,  # 시그니처 호환 — provider 선별로 미사용
    by: Literal["time", "distance"] = "distance",
    limit: int = 20,
    today: datetime.date | None = None,
    hybrid: bool = False,
    vault_path: Path | None = None,
) -> WhatDidIThinkResult:
    """주제에 대한 과거 사고 회상 (provider 선별, 로컬 임베딩 제거 — 020).

    Parameters
    ----------
    by:
        ``"distance"`` (기본) — provider 선별 카드 + Claude 정리 답변.
        ``"time"`` — period_end desc 시간순 정렬 + 분기 그룹 (외부 LLM 미호출,
        FR-A1 / specs/002-timeline-recall). EntityIndex.meta 에서 타임라인 메타를 읽는다.
    limit:
        ``by="time"`` 모드에서 출력 카드 최대 수 (기본 20).
    today:
        ``by="time"`` 의 today_fallback 계산용. ``None`` 이면 ``datetime.date.today()``.
    hybrid:
        폐기됨 — provider 선별로 일원화. ``by="time"`` 과의 충돌만 유지.
    """
    if not topic.strip():
        raise ValueError("topic은 빈 문자열일 수 없음")
    if hybrid and by == "time":
        raise ValueError("--timeline and --hybrid conflict — pick one.")

    index = build_entity_index(vault_path=vault_path)

    if by == "time":
        today_resolved = today or datetime.date.today()
        if not index.entries:
            return WhatDidIThinkResult(
                topic=topic,
                answer=_EMPTY_MESSAGE,
                source_ids=[],
            )
        # 타임라인은 전체 카드를 시간 메타로 정렬 (provider 선별 불필요).
        cards = [
            _resolve_sort_ts(
                dict(entry.meta, card_id=entry.slug),
                today_resolved,
                distance=None,
                document=entry.summary,
            )
            for entry in index.entries
        ]
        sorted_cards = _sort_by_time(cards)
        groups = _group_by_quarter(sorted_cards)
        fallback = [c for c in sorted_cards if c.sort_ts_source == "no_time_meta"]
        markdown = _format_timeline_output(groups, limit=limit, fallback_items=fallback)
        source_ids = [c.card_id for c in sorted_cards[:limit] if c.card_id]
        _record_last_answer(
            command="persona.what_did_i_think",
            query=topic,
            source_ids=source_ids,
        )
        return WhatDidIThinkResult(topic=topic, answer=markdown, source_ids=source_ids)

    # distance-mode → recipes.generate("recall") 가 provider 선별과 0건 신호를 소유.
    from synapse_memory.recipes import generate as recipes_generate

    result = recipes_generate(
        _RECALL_RECIPE_NAME,
        inputs={"topic": topic},
        vault_path=vault_path,
        ai_env=ai_env,
        model_override=_task_model(model, "recall", ai_env),
        top_k_override=top_k,
        disable_save=True,
        return_empty_on_no_matches=True,
        include_history=True,
    )
    if not result.source_ids:
        return WhatDidIThinkResult(
            topic=topic,
            answer="자료 없음 — vault에 관련 Entity를 먼저 생성하세요 (`synapse-memory daily`)",
            source_ids=[],
        )
    return WhatDidIThinkResult(
        topic=topic,
        answer=result.answer_markdown,
        source_ids=result.source_ids,
    )


# ---------------------------------------------------------------------------
# decide — 의사결정 코파일럿
# ---------------------------------------------------------------------------


_DECIDE_RECIPE_NAME = "decide"  # 007-persona-recipes — decide() wrapper


@dataclass
class DecideResult:
    situation: str
    answer: str
    profile_used: bool
    source_ids: list[str] = field(default_factory=list)


def decide(
    situation: str,
    *,
    top_k: int = 6,
    model: str | None = None,
    ai_env: AIEnvironment | None = None,
    store: object | None = None,  # 시그니처 호환 — provider 선별로 미사용
    vault_path: Path | None = None,
) -> DecideResult:
    """의사결정 코파일럿 (007-persona-recipes wrapper, provider 선별 — 020).

    내부적으로 ``recipes.pipeline.generate("decide", ...)`` 를 호출한다.
    외부 시그니처와 ``DecideResult`` 반환은 SC-005 회귀 가드로 보존.

    out-of-domain 가드 (020, distance 임계 0.6 폐기):
    - provider 가 0건 선별 → "자료 불충분" 거부 응답. Profile/Entity 인용을 위장한
      generic 추천을 막는 신뢰 가드.
    """
    if not situation.strip():
        raise ValueError("situation은 빈 문자열일 수 없음")

    # recipes pipeline 이 provider 선별 + 0건 guard + 합성을 단일 경로로 처리.
    from synapse_memory.recipes import generate as recipes_generate

    result = recipes_generate(
        _DECIDE_RECIPE_NAME,
        inputs={"situation": situation},
        vault_path=vault_path,
        ai_env=ai_env,
        model_override=_task_model(model, "decide", ai_env),
        top_k_override=top_k,
        disable_save=True,
        return_empty_on_no_matches=True,
    )
    if not result.source_ids:
        return DecideResult(
            situation=situation,
            answer=(
                "관련 과거 자료 불충분 — vault에 비슷한 결정 노트/Entity를 먼저 기록하거나, "
                "`synapse-memory persona update-profile` 로 결정 패턴을 추출하세요. "
                "현재 vault 자료로는 신뢰 가능한 답변 불가 — "
                "Profile/Entity 인용을 위장한 generic 추천을 막기 위해 거부합니다."
            ),
            profile_used=False,
            source_ids=[],
        )
    return DecideResult(
        situation=situation,
        answer=result.answer_markdown,
        profile_used=result.profile_used,
        source_ids=result.source_ids,
    )


def _record_last_answer(
    *,
    command: str,
    query: str,
    source_ids: list[str],
) -> None:
    citations = tuple(
        AnswerCitation(
            target_kind="card",
            target_ref=source_id,
            source_kind="card",
            display_name=source_id,
        )
        for source_id in source_ids
    )
    ref = new_answer_reference(
        command=command,
        query=query,
        citations=citations,
    )
    with contextlib.suppress(OSError, ValueError):
        save_last_answer(ref)
