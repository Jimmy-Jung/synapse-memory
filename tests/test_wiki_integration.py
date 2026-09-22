# tests/test_wiki_integration.py
"""통합 ops 스키마/프롬프트/파싱 (LLM 호출 없이)."""
from __future__ import annotations

import hashlib

import pytest

from synapse_memory.model import Entity, parse_entity, serialize_entity
from synapse_memory.wiki.integration import (
    INTEGRATION_SCHEMA,
    INTEGRATION_SYSTEM,
    PageOp,
    build_integration_prompt,
    parse_ops,
)
from synapse_memory.wiki.rawdoc import RawDoc


def test_schema_is_object_with_operations() -> None:
    assert INTEGRATION_SCHEMA["type"] == "object"
    assert "operations" in INTEGRATION_SCHEMA["properties"]
    properties = INTEGRATION_SCHEMA["properties"]["operations"]["items"]["properties"]
    assert properties["related"]["description"] == "insight/log 전용 legacy relation"
    for relation in (
        "uses",
        "part_of",
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
    assert "반드시 typed relation" in INTEGRATION_SYSTEM
    assert "project/company/concept/profile" in INTEGRATION_SYSTEM
    assert "related 금지" in INTEGRATION_SYSTEM
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
    assert ops[0].page.related == ()
    assert ops[0].page.uses == ("rag",)
    assert ops[0].page.decided_in == ("decision-note",)
    assert ops[0].warnings == ("dropped continuant related: [[rag]]",)
    assert ops[0].page.attrs["role"] == "Maintainer"
    assert ops[0].page.attrs["period_start"] == "2026-07"
    assert ops[0].page.attrs["metrics"][0].name == "coverage"


def test_parse_ops_drops_related_for_continuant_pages() -> None:
    payload = {"operations": [
        {"op": "create", "type": "concept", "slug": "rag", "title": "RAG",
         "body": "본문", "related": ["[[llm]]"]},
    ]}

    ops = parse_ops(payload)

    assert ops[0].page.related == ()
    assert ops[0].warnings == ("dropped continuant related: [[llm]]",)


def test_parse_ops_keeps_related_for_episodic_pages() -> None:
    payload = {"operations": [
        {"op": "create", "type": "insight", "slug": "rag-note", "title": "RAG note",
         "body": "본문", "related": ["[[rag]]"]},
    ]}

    ops = parse_ops(payload)

    assert ops[0].page.related == ("[[rag]]",)
    assert ops[0].warnings == ()


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


def _evidence_payload(evidence: object) -> dict:
    return {"operations": [{
        "op": "create", "type": "project", "slug": "demo", "title": "Demo",
        "body": "프로젝트 요약", "uses": ["[[concept:rag|RAG]]"],
        "relation_evidence": evidence,
    }]}


def test_exact_evidence_is_bound_to_runtime_source_and_roundtrips() -> None:
    quote = "Demo는 RAG를 사용한다."
    doc = RawDoc("claude-code", "claude-code:demo.jsonl", f"앞문장\n{quote}",
                 "2026-09-22", byte_size=300, start_byte=100)
    evidence = {"relation": "uses", "target": "concept:rag", "quote": quote,
                "source": "codex:forged.jsonl", "start_byte": 999, "sha256": "forged"}

    op = parse_ops(_evidence_payload([evidence, evidence]), source_doc=doc,
                   source_text=quote)[0]

    assert op.warnings == ()
    assert len(op.page.relation_evidence) == 1
    recorded = op.page.relation_evidence[0]
    assert recorded.source == doc.ref
    assert (recorded.start_byte, recorded.end_byte) == (100, 300)
    assert (recorded.start_char, recorded.end_char) == (4, 4 + len(quote))
    assert recorded.sha256 == hashlib.sha256(quote.encode("utf-8")).hexdigest()
    rendered = serialize_entity(op.page)
    assert quote not in rendered
    assert "forged" not in rendered
    assert parse_entity(rendered).relation_evidence == op.page.relation_evidence


@pytest.mark.parametrize("evidence", [
    {"relation": "uses", "target": "concept:rag", "quote": "비밀 조작 인용문"},
    {"relation": "uses", "target": "concept:other", "quote": "Demo는 RAG를 사용한다."},
    {"relation": "uses", "target": "project:rag", "quote": "Demo는 RAG를 사용한다."},
    {"relation": "uses", "target": "../rag", "quote": "Demo는 RAG를 사용한다."},
    {"relation": "uses", "target": "", "quote": "Demo는 RAG를 사용한다."},
    {"relation": "uses", "target": "rag\n", "quote": "Demo는 RAG를 사용한다."},
    {"relation": "same_as", "target": "concept:rag", "quote": "Demo는 RAG를 사용한다."},
    {"relation": "uses", "target": "concept:rag", "quote": ""},
    {"relation": "uses", "target": "concept:rag", "quote": " "},
    {"relation": "uses", "target": "concept:rag", "quote": "a" * 2001},
    {"relation": "uses", "target": "concept:rag", "quote": 42},
    {"relation": ["uses"], "target": "concept:rag", "quote": "Demo는 RAG를 사용한다."},
    "invalid",
])
def test_invalid_evidence_does_not_fabricate_provenance_or_log_quote(evidence: object) -> None:
    doc = RawDoc("claude-code", "claude-code:demo.jsonl", "Demo는 RAG를 사용한다.",
                 "2026-09-22", byte_size=300)
    op = parse_ops(_evidence_payload([evidence]), source_doc=doc)[0]
    assert op.page.relation_evidence == ()
    assert op.page.uses == ("[[concept:rag|RAG]]",)
    assert op.warnings
    assert "비밀" not in " ".join(op.warnings)


def test_evidence_requires_original_text_and_current_chunk() -> None:
    quote = "Demo는 RAG를 사용한다."
    evidence = {"relation": "uses", "target": "concept:rag", "quote": quote}
    doc = RawDoc("claude-code", "claude-code:demo.jsonl", quote,
                 "2026-09-22", byte_size=300)
    op = parse_ops(_evidence_payload([evidence]), source_doc=doc,
                   source_text="현재 샘플에는 이 문장이 없다.")[0]
    assert op.page.relation_evidence == ()
    assert op.warnings
    op = parse_ops(_evidence_payload([evidence]), source_doc=doc,
                   source_text=f"{quote} 샘플 안내 문장")[0]
    assert len(op.page.relation_evidence) == 1
    evidence["quote"] = "샘플 안내 문장"
    assert parse_ops(_evidence_payload([evidence]), source_doc=doc,
                     source_text=f"{quote} 샘플 안내 문장")[0].page.relation_evidence == ()


def test_evidence_without_runtime_byte_bounds_is_dropped() -> None:
    quote = "Demo는 RAG를 사용한다."
    payload = _evidence_payload([{"relation": "uses", "target": "concept:rag", "quote": quote}])
    no_context = parse_ops(payload)[0]
    assert no_context.page.relation_evidence == ()
    assert no_context.warnings
    doc = RawDoc("claude-code", "claude-code:demo.jsonl", quote, "2026-09-22")
    op = parse_ops(payload, source_doc=doc)[0]
    assert op.page.relation_evidence == ()
    assert op.warnings


@pytest.mark.parametrize(("relation", "target"), [
    ("uses", "company:acme"),
    ("broader", "parent"),
])
def test_schema_invalid_relation_evidence_is_dropped_without_losing_page(
    relation: str, target: str,
) -> None:
    quote = "비밀 원문 근거"
    doc = RawDoc("claude-code", "claude-code:demo.jsonl", quote,
                 "2026-09-22", byte_size=300)
    payload = _evidence_payload([{"relation": relation, "target": target, "quote": quote}])
    payload["operations"][0][relation] = [target]
    op = parse_ops(payload, source_doc=doc)[0]
    assert op.page.slug == "demo"
    assert getattr(op.page, relation) == (target,)
    assert op.page.relation_evidence == ()
    assert op.warnings
    assert quote not in " ".join(op.warnings)
