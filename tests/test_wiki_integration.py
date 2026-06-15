# tests/test_wiki_integration.py
"""통합 ops 스키마/프롬프트/파싱 (LLM 호출 없이)."""
from __future__ import annotations

from synapse_memory.wiki.integration import (
    INTEGRATION_SCHEMA,
    PageOp,
    build_integration_prompt,
    parse_ops,
)
from synapse_memory.wiki.page import WikiPage


def test_schema_is_object_with_operations() -> None:
    assert INTEGRATION_SCHEMA["type"] == "object"
    assert "operations" in INTEGRATION_SCHEMA["properties"]


def test_build_prompt_includes_text_and_related() -> None:
    related = [WikiPage(type="project", slug="synapse-memory", title="Synapse Memory", body="기존 본문")]
    prompt = build_integration_prompt("새 대화 내용", related)
    assert "새 대화 내용" in prompt
    assert "synapse-memory" in prompt
    assert "기존 본문" in prompt


def test_parse_ops_valid() -> None:
    payload = {"operations": [
        {"op": "update", "type": "project", "slug": "synapse-memory",
         "title": "Synapse Memory", "body": "갱신된 본문",
         "related": ["[[rag]]"], "sources": ["claude-code:s.jsonl"]},
    ]}
    ops = parse_ops(payload)
    assert len(ops) == 1
    assert isinstance(ops[0], PageOp)
    assert ops[0].op == "update"
    assert ops[0].page.slug == "synapse-memory"
    assert ops[0].page.related == ("[[rag]]",)


def test_parse_ops_skips_invalid_entries() -> None:
    payload = {"operations": [
        {"op": "create", "type": "wibble", "slug": "x", "title": "X", "body": "b"},
        {"op": "create", "type": "concept", "slug": "ok", "title": "OK", "body": "b"},
        {"op": "delete", "type": "concept", "slug": "y", "title": "Y", "body": "b"},
    ]}
    ops = parse_ops(payload)
    assert [o.page.slug for o in ops] == ["ok"]


def test_parse_ops_empty_or_malformed() -> None:
    assert parse_ops({}) == []
    assert parse_ops({"operations": "nope"}) == []
