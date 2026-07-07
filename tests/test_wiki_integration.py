# tests/test_wiki_integration.py
"""통합 ops 스키마/프롬프트/파싱 (LLM 호출 없이)."""
from __future__ import annotations

from synapse_memory.model import Entity
from synapse_memory.wiki.integration import (
    INTEGRATION_SCHEMA,
    INTEGRATION_SYSTEM,
    PageOp,
    build_integration_prompt,
    parse_ops,
)


def test_schema_is_object_with_operations() -> None:
    assert INTEGRATION_SCHEMA["type"] == "object"
    assert "operations" in INTEGRATION_SCHEMA["properties"]
    properties = INTEGRATION_SCHEMA["properties"]["operations"]["items"]["properties"]
    for relation in (
        "uses",
        "part_of",
        "about",
        "decided_in",
        "supersedes",
        "same_as",
    ):
        assert properties[relation] == {"type": "array", "items": {"type": "string"}}
    assert properties["role"] == {"type": "string"}
    assert properties["period_start"] == {"type": "string"}
    assert properties["metrics"]["items"]["properties"]["name"] == {"type": "string"}
    assert properties["resume_language"]["enum"] == [
        "ko",
        "en",
        "ja",
        "zh",
        "한국어",
        "English",
    ]


def test_build_prompt_includes_text_and_related() -> None:
    related = [Entity(type="project", slug="synapse-memory", title="Synapse Memory", body="기존 본문")]
    prompt = build_integration_prompt("새 대화 내용", related)
    assert "새 대화 내용" in prompt
    assert "synapse-memory" in prompt
    assert "기존 본문" in prompt


def test_system_prompt_describes_typed_relation_ranges() -> None:
    assert "uses" in INTEGRATION_SYSTEM
    assert "concept만 허용" in INTEGRATION_SYSTEM
    assert "decided_in" in INTEGRATION_SYSTEM
    assert "insight 또는 log만 허용" in INTEGRATION_SYSTEM
    assert "period_start" in INTEGRATION_SYSTEM
    assert "resume_language" in INTEGRATION_SYSTEM
    assert "metrics" in INTEGRATION_SYSTEM


def test_build_prompt_injects_source_date() -> None:
    prompt = build_integration_prompt("내용", [], source_date="2026-06-16")
    assert "2026-06-16" in prompt
    assert "원본 기록일" in prompt


def test_build_prompt_omits_date_block_when_absent() -> None:
    assert "원본 기록일" not in build_integration_prompt("내용", [])


def test_parse_ops_valid() -> None:
    payload = {"operations": [
        {"op": "update", "type": "project", "slug": "synapse-memory",
         "title": "Synapse Memory", "body": "갱신된 본문",
         "related": ["[[rag]]"], "uses": ["rag"], "decided_in": ["decision-note"],
         "role": "Maintainer", "period_start": "2026-07",
         "metrics": [{"name": "coverage", "value": "80%+"}],
         "sources": ["claude-code:s.jsonl"]},
    ]}
    ops = parse_ops(payload)
    assert len(ops) == 1
    assert isinstance(ops[0], PageOp)
    assert ops[0].op == "update"
    assert ops[0].page.slug == "synapse-memory"
    assert ops[0].page.related == ("[[rag]]",)
    assert ops[0].page.uses == ("rag",)
    assert ops[0].page.decided_in == ("decision-note",)
    assert ops[0].page.attrs["role"] == "Maintainer"
    assert ops[0].page.attrs["period_start"] == "2026-07"
    assert ops[0].page.attrs["metrics"][0].name == "coverage"


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
