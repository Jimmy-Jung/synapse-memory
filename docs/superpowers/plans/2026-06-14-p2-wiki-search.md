# P2 — Wiki-first 검색 + 답변 환원 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 executing-plans. TDD, 태스크별 커밋.

**Goal:** wiki 페이지를 rag에 인덱싱하고, `find_related_pages`에 의미유사도 top-k를 더해 R2를 완성하며, wiki-first로 질문에 답하고(인용 포함) 가치 있는 답을 Insights 페이지로 환원(write-back)한다 — "질문할수록 똑똑해지는" 루프.

**Architecture:** rag(`open_vector_store`/`embed_query`/`embed_texts`/`hybrid_search`/`VectorRecord`)를 재사용하되 **대상을 카드가 아닌 wiki 페이지**로 둔다. wiki 레코드는 `id="wiki:<type>:<slug>"`, `metadata={"source_kind":"wiki","type","slug","title"}`. 검색은 `where={"source_kind":"wiki"}`로 스코프. ingest는 적용 후 변경 페이지를 재인덱싱한다. 답변 환원은 P1의 `save_page`로 insight 페이지를 만들고 인덱싱한다.

**Tech Stack:** P0 `wiki/page.py`, P1 `wiki/ingest.py`·`apply.py`, `synapse_memory.rag.*`, `ai_api.complete`. 테스트는 임베딩/스토어/LLM을 **주입(inject)**해 실제 모델 다운로드 회피.

---

## 범위 메모

- **포함**: wiki 인덱싱, 의미검색 top-k(R2 완성), wiki-first ask + 인용 + write-back, ingest 후 재인덱싱, CLI.
- **제외**: 데몬 트리거(P3), lint(P4), 초기 백필(P5).
- **테스트 격리**: rag 실제 임베딩은 무겁다. 모든 신규 함수는 `store`/`embed_fn`/`semantic_fn`/`_retrieve_wiki`/LLM을 **주입 가능**하게 설계하고, 단위테스트는 가짜(fake)로 검증. rag 부재 시 graceful `[]` fallback.

---

## File Structure

- Create: `src/synapse_memory/wiki/index.py` — `WIKI_SOURCE_KIND`, `wiki_page_to_text`, `wiki_page_to_record`, `index_wiki_pages`, `index_one_page`.
- Modify: `src/synapse_memory/wiki/retrieval.py` — `find_related_pages`에 의미 top-k 병합(주입 가능).
- Modify: `src/synapse_memory/wiki/ingest.py` — apply 후 변경 페이지 재인덱싱(best-effort).
- Create: `src/synapse_memory/wiki/query.py` — `ask_wiki(...)`: wiki 검색 → 합성 → 인용 → 선택적 write-back.
- Modify: `src/synapse_memory/cli.py` — `wiki ask` + `wiki reindex` 서브커맨드.
- Modify: `src/synapse_memory/wiki/__init__.py` — export.
- Test: `tests/test_wiki_index.py`, `test_wiki_retrieval_semantic.py`, `test_wiki_query.py`, `test_cli_wiki.py` (+ `test_wiki_ingest.py` 보강).

---

## Task 1: wiki 인덱싱 (wiki/index.py)

**Files:** Create `src/synapse_memory/wiki/index.py`; Test `tests/test_wiki_index.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_index.py
"""wiki 페이지 → 벡터 레코드 + 인덱싱 (store/embed 주입)."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.index import (
    WIKI_SOURCE_KIND,
    index_wiki_pages,
    wiki_page_to_record,
    wiki_page_to_text,
)
from synapse_memory.wiki.page import WikiPage, save_page


class FakeStore:
    def __init__(self): self.records = []
    def upsert(self, records): self.records.extend(records); return len(records)


def _embed(texts): return [[float(len(t))] for t in texts]


def test_page_to_text_includes_title_and_body() -> None:
    page = WikiPage(type="concept", slug="rag", title="RAG", body="검색 증강")
    text = wiki_page_to_text(page)
    assert "RAG" in text and "검색 증강" in text


def test_page_to_record_id_and_metadata() -> None:
    page = WikiPage(type="project", slug="synapse-memory", title="Synapse Memory", body="b")
    rec = wiki_page_to_record(page, embedding=[1.0])
    assert rec.id == "wiki:project:synapse-memory"
    assert rec.metadata["source_kind"] == WIKI_SOURCE_KIND
    assert rec.metadata["type"] == "project"
    assert rec.metadata["slug"] == "synapse-memory"
    assert rec.metadata["title"] == "Synapse Memory"


def test_index_wiki_pages_upserts_all(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG", body="a"), vault_path=tmp_path)
    save_page(WikiPage(type="project", slug="sm", title="SM", body="b"), vault_path=tmp_path)
    store = FakeStore()
    n = index_wiki_pages(vault_path=tmp_path, store=store, embed_fn=_embed)
    assert n == 2
    assert {r.id for r in store.records} == {"wiki:concept:rag", "wiki:project:sm"}
```

- [ ] **Step 2:** `uv run pytest tests/test_wiki_index.py -v` → fail.
- [ ] **Step 3: implement** `src/synapse_memory/wiki/index.py`:
  - `WIKI_SOURCE_KIND = "wiki"`.
  - `wiki_page_to_text(page) -> str`: `f"{page.title}\n\n{page.body}"`.
  - `wiki_page_to_record(page, *, embedding) -> VectorRecord`: id `f"wiki:{page.type}:{page.slug}"`, document=wiki_page_to_text, metadata `{"source_kind": WIKI_SOURCE_KIND, "type": page.type, "slug": page.slug, "title": page.title}`. `from synapse_memory.rag import VectorRecord`.
  - `index_wiki_pages(*, vault_path=None, store=None, embed_fn=None) -> int`: 모든 `VALID_TYPES` `list_pages` 수집 → 텍스트 임베딩(`embed_fn or embed_texts`) → 레코드 → `(store or open_vector_store()).upsert(records)`. 0개면 0.
  - `index_one_page(page, *, store=None, embed_fn=None) -> None`: 단일 upsert.
- [ ] **Step 4:** pass (3). **Step 5:** commit `feat(wiki): index wiki pages into vector store (injectable store/embed)`.

---

## Task 2: 의미 top-k 병합 (retrieval 업그레이드)

**Files:** Modify `src/synapse_memory/wiki/retrieval.py`; Test `tests/test_wiki_retrieval_semantic.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_retrieval_semantic.py
from __future__ import annotations
from pathlib import Path
from synapse_memory.wiki.page import WikiPage, save_page
from synapse_memory.wiki.retrieval import find_related_pages


def test_semantic_retriever_adds_pages(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG", body="검색 증강 생성"), vault_path=tmp_path)
    def fake_semantic(text, *, vault_path, top_k):
        return ["rag"]
    hits = find_related_pages("임베딩 기반 문서 검색", vault_path=tmp_path, semantic_fn=fake_semantic)
    assert "rag" in {p.slug for p in hits}


def test_semantic_none_uses_name_match_only(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    hits = find_related_pages("RAG 작업", vault_path=tmp_path, semantic_fn=None)
    assert "rag" in {p.slug for p in hits}
```

- [ ] **Step 2:** fail. **Step 3: implement** — `find_related_pages(text, *, vault_path=None, max_pages=DEFAULT_MAX_PAGES, semantic_fn=_DEFAULT)`:
  - sentinel 기본값(`_DEFAULT = object()`). 미지정이면 `_default_semantic` 사용, `None`이면 의미검색 끔, 함수면 그걸 사용.
  - 이름매칭 + 1-hop 유지. semantic이 켜지면 `slugs = semantic_fn(text, vault_path=vault_path, top_k=max_pages)` → 각 slug를 all_pages에서 찾아 매칭집합에 추가(이름매칭 결과 뒤에), 그 페이지도 1-hop 확장. dedup + max_pages.
  - `_default_semantic(text, *, vault_path, top_k)`: 지연 import `from synapse_memory.rag import open_vector_store, embed_query`; `store.query(embed_query(text), top_k=top_k, where={"source_kind":"wiki"})` → metadata["slug"] 목록. 예외/부재 시 `[]`.
- [ ] **Step 4:** pass + `test_wiki_retrieval.py` 회귀 통과. **Step 5:** commit `feat(wiki): add semantic top-k to find_related_pages (R2 complete)`.

> 주의: 기존 `test_wiki_retrieval.py`는 `semantic_fn`을 안 넘긴다. 그 테스트들이 rag 실 호출로 깨지지 않게 — `_default_semantic`은 rag 부재/빈 store에서 `[]`를 반환해야 하고, 테스트 환경(빈 chroma)에서도 안전해야 한다. 필요하면 기존 retrieval 테스트에 `semantic_fn=None`을 추가해 격리.

---

## Task 3: ingest 후 재인덱싱

**Files:** Modify `src/synapse_memory/wiki/ingest.py`; 보강 `tests/test_wiki_ingest.py`.

- [ ] **Step 1: failing test** (기존 헬퍼 `_write_session`, `_fake_complete_structured` 재사용)
```python
def test_ingest_reindexes_written_pages(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "s", "RAG 정리")
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured",
        _fake_complete_structured({"operations": [
            {"op":"create","type":"concept","slug":"rag","title":"RAG","body":"b"}]}))
    seen = []
    monkeypatch.setattr(ingest_mod, "index_one_page", lambda page, **kw: seen.append(page.slug))
    ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                  watermark_path=state, ai_env=None, today="2026-06-14")
    assert "rag" in seen
```

- [ ] **Step 2:** fail. **Step 3: implement** — ingest.py: `from synapse_memory.wiki.index import index_one_page` + `import contextlib`. apply 성공(non-dry-run) 후, 적용된 ops의 페이지마다 `with contextlib.suppress(Exception): index_one_page(op.page)`. rag 부재해도 ingest 성공 유지.
- [ ] **Step 4:** pass + ingest 회귀. **Step 5:** commit `feat(wiki): reindex written pages after ingest (best-effort)`.

---

## Task 4: wiki-first ask + write-back (wiki/query.py)

**Files:** Create `src/synapse_memory/wiki/query.py`; Test `tests/test_wiki_query.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_wiki_query.py
from __future__ import annotations
import datetime
from pathlib import Path
import synapse_memory.wiki.query as q
from synapse_memory.wiki.page import WikiPage, save_page, load_page


def test_ask_wiki_synthesizes_with_citation(tmp_path, monkeypatch) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG", body="검색 증강 생성"), vault_path=tmp_path)
    monkeypatch.setattr(q, "_retrieve_wiki",
        lambda query, *, vault_path, top_k: [load_page("concept", "rag", vault_path=vault_path)])
    monkeypatch.setattr(q.ai_api, "complete", lambda *a, **k: "RAG는 검색 증강 생성입니다 [[rag]]")
    res = q.ask_wiki("RAG가 뭐야?", vault_path=tmp_path)
    assert "RAG" in res.answer
    assert "rag" in res.sources


def test_ask_wiki_writeback_creates_insight(tmp_path, monkeypatch) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG", body="x"), vault_path=tmp_path)
    monkeypatch.setattr(q, "_retrieve_wiki",
        lambda query, *, vault_path, top_k: [load_page("concept", "rag", vault_path=vault_path)])
    monkeypatch.setattr(q.ai_api, "complete", lambda *a, **k: "답변 본문 [[rag]]")
    monkeypatch.setattr(q, "index_one_page", lambda page, **kw: None)
    res = q.ask_wiki("RAG 설명", vault_path=tmp_path, save=True, today="2026-06-14")
    assert res.saved_slug is not None
    insight = load_page("insight", res.saved_slug, vault_path=tmp_path, when=datetime.date(2026, 6, 14))
    assert "답변 본문" in insight.body


def test_ask_wiki_no_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(q, "_retrieve_wiki", lambda query, *, vault_path, top_k: [])
    res = q.ask_wiki("아무거나", vault_path=tmp_path)
    assert res.sources == []
    assert "없" in res.answer  # "자료에 없음"
```

- [ ] **Step 2:** fail. **Step 3: implement** `src/synapse_memory/wiki/query.py`:
  - `@dataclass class WikiAnswer: query: str; answer: str; sources: list[str]; saved_slug: str | None = None`.
  - `ASK_WIKI_SYSTEM`: 제공된 wiki 페이지만 근거, 각 주장에 `[[slug]]` 인용, 자료 없으면 "자료에 없음", 한국어, 짧고 정확.
  - `_retrieve_wiki(query, *, vault_path=None, top_k=5) -> list[WikiPage]`: 지연 import rag; `store.query(embed_query(query), top_k, where={"source_kind":"wiki"})` → 각 metadata(type, slug)로 `load_page` (실패 skip). rag 부재/오류 → `[]`.
  - `ask_wiki(query, *, vault_path=None, top_k=5, model=None, ai_env=None, save=False, today=None) -> WikiAnswer`:
    1. `pages = _retrieve_wiki(query, vault_path=vault_path, top_k=top_k)`. 빈 목록이면 `WikiAnswer(query, "자료에 없음 — 먼저 ingest/reindex 하세요.", [])`.
    2. context = 각 page `f"[[{page.slug}]] {page.title}\n{page.body[:2000]}"` join. user prompt.
    3. `answer = ai_api.complete(prompt, system=ASK_WIKI_SYSTEM, model=model, env=ai_env, timeout=120)`.
    4. `cited = extract_wikilinks(answer)`; `sources = list(dict.fromkeys(cited + [p.slug for p in pages if p.slug in answer]))` — 우선 인용된 slug. (최소: `sources = extract_wikilinks(answer)` 우선, 비면 retrieved slug.)
    5. save=True면: `slug = slugify(query)[:60] or "insight"`; insight WikiPage(type="insight", slug, title=query, body=answer, related=tuple(f"[[{s}]]" for s in sources), sources=("ask",), updated=today or date.today().isoformat()); `save_page`; best-effort `index_one_page`; `saved_slug=slug`.
  - import: `from synapse_memory.wiki.page import WikiPage, load_page, save_page, slugify, extract_wikilinks`; `from synapse_memory.wiki.index import index_one_page`; `from synapse_memory.llm import ai_api`; `from datetime import date`.
- [ ] **Step 4:** pass (3). **Step 5:** commit `feat(wiki): add wiki-first ask with citations + insight write-back`.

---

## Task 5: CLI + reindex + 회귀

**Files:** Modify `src/synapse_memory/cli.py`, `wiki/__init__.py`; Test `tests/test_cli_wiki.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_cli_wiki.py
import synapse_memory.cli as cli
from synapse_memory.wiki.query import WikiAnswer


def test_cli_wiki_ask(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask_wiki",
        lambda query, **kw: WikiAnswer(query=query, answer="답", sources=["rag"]))
    rc = cli.main(["wiki", "ask", "RAG가 뭐야?"])
    assert rc == 0
    assert "답" in capsys.readouterr().out


def test_cli_wiki_reindex(monkeypatch, capsys):
    monkeypatch.setattr(cli, "index_wiki_pages", lambda **kw: 7)
    rc = cli.main(["wiki", "reindex"])
    assert rc == 0
    assert "7" in capsys.readouterr().out
```

- [ ] **Step 2:** fail. **Step 3: implement** — cli.py 상단 import `from synapse_memory.wiki.query import ask_wiki`, `from synapse_memory.wiki.index import index_wiki_pages`. `build_parser`에 `wiki` 서브파서 + 액션 `ask`(positional `query`, `--save` 플래그) / `reindex` 등록(기존 `card`처럼 `add_subparsers(dest="action")` 패턴). `cmd_wiki_ask(args)`: `res = ask_wiki(args.query, save=getattr(args,"save",False))`; `print(res.answer)`; sources 있으면 출력; return 0. `cmd_wiki_reindex(args)`: `print(f"indexed {index_wiki_pages()} pages")`; return 0. (기존 `endpoints/ask.py`/`/sm:ask`는 건드리지 않음.)
- [ ] **Step 4:** `uv run pytest -q` 전체 통과 + `ruff check src/synapse_memory/wiki src/synapse_memory/cli.py tests/test_wiki_*.py tests/test_cli_wiki.py` clean. **Step 5:** commit `feat(cli): add 'wiki ask' + 'wiki reindex' subcommands`.

---

## Self-Review
- **Spec coverage:** spec 019 §6(wiki-first 검색·인용·write-back), R2 의미유사도 완성(Task 2), rag 재조준(Task 1 wiki 인덱싱 + where 스코프), 누적 루프(write-back→재인덱싱 Task 3·4). 데몬/lint/백필 제외(범위 메모).
- **테스트 격리:** 모든 신규 함수가 store/embed/semantic/retrieve/LLM 주입 가능 → 실제 모델 다운로드 없이 단위테스트. rag 부재 graceful `[]`.
- **Type consistency:** `WIKI_SOURCE_KIND="wiki"`, id `wiki:<type>:<slug>`, `find_related_pages(..., semantic_fn=_DEFAULT)`, `index_wiki_pages/index_one_page`, `_retrieve_wiki(query,*,vault_path,top_k)`, `ask_wiki(...)->WikiAnswer(query,answer,sources,saved_slug)`가 전 태스크 일관. rag 계약(`open_vector_store`,`embed_query`,`embed_texts`,`VectorRecord(id,document,embedding,metadata)`,`store.query(vec,top_k,where)`)은 endpoints/ask.py 확인치와 일치.
- **회귀 주의:** 기존 `test_wiki_retrieval.py`가 rag 실호출로 깨지지 않도록 `_default_semantic`은 빈/부재 store에서 `[]` 보장.
