# tests/test_provider_retrieval_020.py
"""020 — provider-only retrieval: page_index + select_related + bounded limit.

로컬 임베딩 제거 후 LLM-as-retriever 경로와 메모리 천장(limit) 검증.
provider 호출은 ai_api.complete_structured를 monkeypatch해 hermetic하게 유지.
"""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.wiki import ingest as ingest_mod
from synapse_memory.wiki import llm_retrieval as lr
from synapse_memory.wiki.ingest import ingest_source
from synapse_memory.wiki.page import WikiPage
from synapse_memory.wiki.page_index import PageIndex, build_page_index


# ---------- page_index ----------

def test_build_page_index_sorts_and_summarizes() -> None:
    pages = [
        WikiPage(type="concept", slug="zeta", title="Zeta", body="z" * 500),
        WikiPage(type="concept", slug="alpha", title="Alpha", body="짧은 본문"),
    ]
    idx = build_page_index(pages, summary_chars=50)
    assert [e.slug for e in idx.entries] == ["alpha", "zeta"]  # slug 정렬
    assert idx.entries[1].summary.endswith("…")  # 500자 → 트렁케이트
    assert len(idx.entries[1].summary) <= 51
    assert idx.slugs == {"alpha", "zeta"}


def test_page_index_render_lines() -> None:
    idx = build_page_index(
        [WikiPage(type="concept", slug="rag", title="RAG", body="검색 증강")]
    )
    rendered = idx.render()
    assert "[rag] RAG — 검색 증강" == rendered


# ---------- select_related ----------

def _fake_structured(returns):
    def _fn(prompt, *, system=None, model=None, json_schema=None, env=None,
            timeout=120, provider=None, **kw):
        return returns
    return _fn


def test_select_related_filters_to_valid_slugs(monkeypatch) -> None:
    idx = build_page_index([
        WikiPage(type="concept", slug="rag", title="RAG", body="b"),
        WikiPage(type="concept", slug="mcp", title="MCP", body="b"),
    ])
    # provider가 환각 slug("ghost") 섞어 반환 → 인덱스 존재분만 통과.
    monkeypatch.setattr(
        lr.ai_api, "complete_structured",
        _fake_structured({"related": ["rag", "ghost", "mcp", "rag"]}),
    )
    out = lr.select_related("문서 본문", idx, max_pages=10)
    assert out == ["rag", "mcp"]  # ghost 제거 + dedup


def test_select_related_empty_index_returns_empty(monkeypatch) -> None:
    called = {"n": 0}

    def _spy(*a, **k):
        called["n"] += 1
        return {"related": []}

    monkeypatch.setattr(lr.ai_api, "complete_structured", _spy)
    assert lr.select_related("문서", PageIndex(entries=())) == []
    assert called["n"] == 0  # 빈 인덱스면 provider 호출조차 안 함


def test_select_related_graceful_on_provider_error(monkeypatch) -> None:
    def _boom(*a, **k):
        raise RuntimeError("provider down")

    idx = build_page_index([WikiPage(type="concept", slug="rag", title="RAG", body="b")])
    monkeypatch.setattr(lr.ai_api, "complete_structured", _boom)
    assert lr.select_related("문서", idx) == []  # 예외 삼키고 [] (ingest 진행 보존)


def test_select_related_respects_max_pages(monkeypatch) -> None:
    pages = [WikiPage(type="concept", slug=f"c{i}", title=f"C{i}", body="b") for i in range(5)]
    idx = build_page_index(pages)
    monkeypatch.setattr(
        lr.ai_api, "complete_structured",
        _fake_structured({"related": [f"c{i}" for i in range(5)]}),
    )
    assert len(lr.select_related("문서", idx, max_pages=2)) == 2


# ---------- bounded limit (메모리 천장) ----------

def _write_session(root: Path, name: str, text: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.jsonl").write_text(
        json.dumps({"message": {"content": text}}) + "\n", encoding="utf-8"
    )


def test_ingest_limit_caps_docs_processed(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    for i in range(5):
        _write_session(raw_root, f"s{i}", f"세션 {i} 내용")
    # 통합/선별 LLM은 빈 ops 반환(디스크 변경 없음, 핫경로만 검증).
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured",
                        lambda *a, **k: {"operations": []})
    state = tmp_path / "wm.json"
    result = ingest_source(
        "claude-code", vault_path=tmp_path, raw_root=raw_root,
        watermark_path=state, today="2026-06-16", limit=2,
    )
    assert result.docs_processed == 2  # limit으로 사이클당 상한
