# src/synapse_memory/wiki/integration.py
"""통합(integrate-not-index) 프롬프트 + 출력 스키마 + ops 파싱.

엔진은 complete_structured(json_schema=INTEGRATION_SCHEMA)로 페이지 작업 목록을 반환.
여기서는 LLM을 부르지 않고 프롬프트 구성과 응답(dict)→list[PageOp] 검증만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse_memory.model import render_schema_guidance
from synapse_memory.model.entity import RELATION_FIELDS
from synapse_memory.wiki.page import VALID_TYPES, WikiPage, serialize_page

VALID_OPS = ("create", "update")

INTEGRATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": list(VALID_OPS)},
                    "type": {"type": "string", "enum": list(VALID_TYPES)},
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "related": {"type": "array", "items": {"type": "string"}},
                    **{
                        relation: {"type": "array", "items": {"type": "string"}}
                        for relation in RELATION_FIELDS
                    },
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["op", "type", "slug", "title", "body"],
            },
        }
    },
    "required": ["operations"],
}

INTEGRATION_SYSTEM = f"""당신은 사용자의 개인 wiki를 유지하는 사서입니다.
'관련 기존 페이지'를 보고 새 대화 내용을 통합하세요.

규칙:
- 관련된 기존 페이지가 있으면 새로 만들지 말고 그것을 갱신(op=update)하세요.
- 정말 새로운 엔티티/개념일 때만 op=create.
- body는 갱신/생성될 페이지의 전체 마크다운 본문(frontmatter 제외)입니다.
- 연결은 가능한 한 typed relation 필드로 분류하고, 값은 "slug" 문자열 목록으로 넣으세요.
- uses: 대상 range는 concept만 허용합니다. 예: project "synapse-memory"가 concept "rag"를 쓰면 uses=["rag"].
- decided_in: 대상 range는 insight 또는 log만 허용합니다. 예: project "synapse-memory" 결정이 insight "2026-07-provider-only"에 기록되면 decided_in=["2026-07-provider-only"].
- part_of, about, supersedes, same_as: 대상 range는 project/company/concept/insight/log/profile 모두 허용합니다.
  예: concept "bm25"가 concept "retrieval"에 속하면 part_of=["retrieval"].
  예: insight "resume-flow-note"가 project "synapse-memory" 주제라면 about=["synapse-memory"].
  예: 새 profile "ai-workflow-v2"가 오래된 "ai-workflow-v1"을 대체하면 supersedes=["ai-workflow-v1"].
  예: concept "retrieval-augmented-generation"이 concept "rag"와 같으면 same_as=["rag"].
- related는 insight/log의 기존 flat 관련 필드를 유지해야 할 때만 사용하고, project/concept/company/profile의 새 연결은 typed relation을 우선합니다.
- 통합할 내용이 없으면 operations를 빈 배열로 반환하세요.
출력은 반드시 주어진 JSON 스키마를 따릅니다.

{render_schema_guidance()}"""


@dataclass(frozen=True)
class PageOp:
    """검증된 한 페이지 작업."""

    op: str
    page: WikiPage


def build_integration_prompt(
    text: str, related: list[WikiPage], *, source_date: str | None = None
) -> str:
    """엔진에 보낼 user 프롬프트 (새 내용 + 관련 기존 페이지 전문).

    ``source_date``(YYYY-MM-DD)가 주어지면 — 원본이 기록된 날 — 제목/slug에
    날짜를 박을 때 처리일(오늘) 대신 이 날짜를 쓰도록 명시한다. activity-log류는
    본문이 상대 타임스탬프(00:00:00~)만 담아, 날짜를 안 주면 LLM이 자기 오늘로
    채워 넣어 며칠 어긋난 노트명이 생긴다.
    """
    related_block = (
        "\n\n".join(serialize_page(p) for p in related)
        if related
        else "(관련 기존 페이지 없음)"
    )
    date_block = (
        f"# 원본 기록일\n"
        f"이 내용은 {source_date}에 기록되었다. 제목(title)이나 slug에 날짜를 넣을 때는 "
        f"반드시 이 날짜({source_date})를 사용한다. 오늘/처리 날짜를 쓰지 않는다.\n\n"
        if source_date
        else ""
    )
    return (
        f"{date_block}"
        f"# 새 대화/노트 내용\n{text}\n\n"
        f"# 관련 기존 페이지 (있으면 갱신 대상)\n{related_block}\n\n"
        f"위 내용을 wiki에 통합하는 operations를 반환하세요."
    )


def parse_ops(payload: Any) -> list[PageOp]:
    """엔진 응답(dict) → 검증된 PageOp 목록. 잘못된 항목은 skip."""
    if not isinstance(payload, dict):
        return []
    raw_ops = payload.get("operations")
    if not isinstance(raw_ops, list):
        return []
    ops: list[PageOp] = []
    for entry in raw_ops:
        if not isinstance(entry, dict):
            continue
        op = entry.get("op")
        if op not in VALID_OPS:
            continue
        page_type = entry.get("type")
        slug = entry.get("slug")
        title = entry.get("title")
        if page_type not in VALID_TYPES or not slug or not title:
            continue
        page = WikiPage(
            type=str(page_type),
            slug=str(slug),
            title=str(title),
            related=tuple(str(x) for x in (entry.get("related") or [])),
            sources=tuple(str(x) for x in (entry.get("sources") or [])),
            **{
                relation: tuple(str(x) for x in (entry.get(relation) or []))
                for relation in RELATION_FIELDS
            },
            body=str(entry.get("body", "")),
        )
        ops.append(PageOp(op=op, page=page))
    return ops
