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
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["op", "type", "slug", "title", "body"],
            },
        }
    },
    "required": ["operations"],
}

INTEGRATION_SYSTEM = """당신은 사용자의 개인 wiki를 유지하는 사서입니다.
'관련 기존 페이지'를 보고 새 대화 내용을 통합하세요.

규칙:
- 관련된 기존 페이지가 있으면 새로 만들지 말고 그것을 갱신(op=update)하세요.
- 정말 새로운 엔티티/개념일 때만 op=create.
- body는 갱신/생성될 페이지의 전체 마크다운 본문(frontmatter 제외)입니다.
- related에는 연결할 다른 페이지를 "[[slug]]" 형식으로 넣으세요.
- 통합할 내용이 없으면 operations를 빈 배열로 반환하세요.
출력은 반드시 주어진 JSON 스키마를 따릅니다."""


@dataclass(frozen=True)
class PageOp:
    """검증된 한 페이지 작업."""

    op: str
    page: WikiPage


def build_integration_prompt(text: str, related: list[WikiPage]) -> str:
    """엔진에 보낼 user 프롬프트 (새 내용 + 관련 기존 페이지 전문)."""
    related_block = (
        "\n\n".join(serialize_page(p) for p in related)
        if related
        else "(관련 기존 페이지 없음)"
    )
    return (
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
            body=str(entry.get("body", "")),
        )
        ops.append(PageOp(op=op, page=page))
    return ops
