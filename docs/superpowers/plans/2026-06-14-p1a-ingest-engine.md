# P1a — Ingest Engine (Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `synapse-memory ingest --now`로, claude-code 대화 raw를 읽어 관련 기존 wiki 페이지를 찾고, LLM으로 **통합(integrate-not-index)**해 페이지를 갱신/생성하고 양방향 링크 + `log.md`를 남기는 핵심 ingest 루프를 손으로 검증 가능하게 만든다.

**Architecture:** P0의 `WikiPage`/`save_page`/`with_related` 위에 6개 작은 모듈을 얹는다. 엔진(claude/codex CLI)은 `ai_api.complete_structured(json_schema=...)`로 **페이지 작업 목록(ops JSON)**을 반환하고, Python이 검증 후 `save_page`로 적용한다(현 어댑터는 순수 텍스트 in/out — agentic 파일편집 불가, 그래서 구조화 출력이 정답). P1a는 단일 소스(claude-code) + 이름매칭/1-hop 선별만 한다(의미유사도 인덱싱은 P2).

**Tech Stack:** Python 3.11+, `ai_api.complete_structured`, P0 `wiki/page.py`, `storage.l0.l0_root`(테스트는 `SYNAPSE_L0_ROOT`로 자동 격리), `pytest`.

---

## 범위 메모 (Scope notes)

- **소스**: claude-code만 (`~/.synapse/private/raw/claude-code/**/*.jsonl`). 멀티소스는 후속.
- **선별(R2 부분구현)**: 이름매칭 + 링크 1-hop. **의미유사도 top-k 인덱싱은 P2**(rag 재조준과 함께).
- **redaction 없음** (D4): raw를 그대로 엔진에 전달.
- **트리거 없음**: `ingest --now` 수동 호출만. launchd 데몬은 P3.
- **lint 없음**: 양방향 링크의 *즉시* 보강만 적용(끊긴 링크 전체 점검은 P4).
- **불변성**: 모든 모듈은 P0 패턴(frozen dataclass, 새 객체 반환)을 따른다.

---

## File Structure

- Create: `src/synapse_memory/wiki/watermark.py` — ingest 진행상태(`~/.synapse/private/ingest_state.json`) load/save.
- Create: `src/synapse_memory/wiki/rawdoc.py` — claude-code jsonl → `RawDoc`(텍스트+ref+mtime), watermark 이후만.
- Create: `src/synapse_memory/wiki/retrieval.py` — `find_related_pages(text)`: 이름매칭 + 1-hop 링크 확장.
- Create: `src/synapse_memory/wiki/integration.py` — `INTEGRATION_SCHEMA`, 프롬프트 빌더, ops 파싱/검증 → `list[PageOp]`.
- Create: `src/synapse_memory/wiki/apply.py` — `apply_ops`: `save_page` + 양방향 링크.
- Create: `src/synapse_memory/wiki/log.py` — `append_log`: vault 루트 `log.md`에 시간순 1줄.
- Create: `src/synapse_memory/wiki/ingest.py` — `ingest_source(...)` 오케스트레이터 (dry-run/limit).
- Modify: `src/synapse_memory/cli.py` — `ingest` 서브커맨드 + `cmd_ingest`.
- Modify: `src/synapse_memory/wiki/__init__.py` — 신규 공개 함수 export.
- Test: `tests/test_wiki_watermark.py`, `test_wiki_rawdoc.py`, `test_wiki_retrieval.py`, `test_wiki_integration.py`, `test_wiki_apply.py`, `test_wiki_log.py`, `test_wiki_ingest.py`, `test_cli_ingest.py`.

각 파일 1책임. `ingest.py`만 조립자이고 나머지는 순수 단위.

---

## Task 1: watermark — ingest 진행상태

**Files:**
- Create: `src/synapse_memory/wiki/watermark.py`
- Test: `tests/test_wiki_watermark.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_watermark.py
"""ingest watermark load/save."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.watermark import load_watermark, save_watermark


def test_load_missing_returns_none(tmp_path: Path) -> None:
    assert load_watermark("claude-code", path=tmp_path / "state.json") is None


def test_save_then_load(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    save_watermark("claude-code", "2026-06-14T10:00:00", path=p)
    assert load_watermark("claude-code", path=p) == "2026-06-14T10:00:00"


def test_save_is_per_source(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    save_watermark("claude-code", "2026-06-14T10:00:00", path=p)
    save_watermark("obsidian", "2026-06-13T09:00:00", path=p)
    assert load_watermark("claude-code", path=p) == "2026-06-14T10:00:00"
    assert load_watermark("obsidian", path=p) == "2026-06-13T09:00:00"


def test_corrupt_file_treated_as_empty(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text("not json", encoding="utf-8")
    assert load_watermark("claude-code", path=p) is None
```

- [ ] **Step 2: Run → fails** (`ModuleNotFoundError: synapse_memory.wiki.watermark`)
Run: `uv run pytest tests/test_wiki_watermark.py -v`

- [ ] **Step 3: Implement**

```python
# src/synapse_memory/wiki/watermark.py
"""ingest 진행상태 — 소스별 마지막 처리 시각(ISO).

저장: ``~/.synapse/private/ingest_state.json`` (l0_root 하위).
형식: {"<source>": "<iso8601>"}.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

STATE_FILENAME = "ingest_state.json"


def default_state_path() -> Path:
    return l0_root() / STATE_FILENAME


def _load_all(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_watermark(source: str, *, path: Path | None = None) -> str | None:
    """소스의 마지막 처리 ISO 시각. 없으면 None."""
    state = _load_all(path or default_state_path())
    value = state.get(source)
    return str(value) if value else None


def save_watermark(source: str, iso: str, *, path: Path | None = None) -> None:
    """소스의 처리 시각 갱신 (다른 소스 보존)."""
    target = path or default_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    state = _load_all(target)
    state[source] = iso
    target.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

- [ ] **Step 4: Run → pass** (`uv run pytest tests/test_wiki_watermark.py -v` → 4 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/watermark.py tests/test_wiki_watermark.py
git commit -m "feat(wiki): add ingest watermark state (per-source)"
```

---

## Task 2: rawdoc — claude-code jsonl 읽기 (watermark 이후)

**Files:**
- Create: `src/synapse_memory/wiki/rawdoc.py`
- Test: `tests/test_wiki_rawdoc.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_rawdoc.py
"""claude-code 미러 jsonl → RawDoc."""
from __future__ import annotations

import json
import os
from pathlib import Path

from synapse_memory.wiki.rawdoc import RawDoc, iter_new_raw


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events),
        encoding="utf-8",
    )


def test_extracts_text_from_message_events(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    f = root / "projects" / "demo" / "sess1.jsonl"
    _write_jsonl(
        f,
        [
            {"type": "user", "message": {"role": "user", "content": "프로젝트 구조 알려줘"}},
            {"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "text", "text": "MVVM 입니다"}]}},
        ],
    )
    docs = iter_new_raw("claude-code", since=None, root=root)
    assert len(docs) == 1
    assert isinstance(docs[0], RawDoc)
    assert "프로젝트 구조 알려줘" in docs[0].text
    assert "MVVM 입니다" in docs[0].text
    assert docs[0].ref == "claude-code:projects/demo/sess1.jsonl"


def test_since_filters_older_files(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    old = root / "old.jsonl"
    new = root / "new.jsonl"
    _write_jsonl(old, [{"message": {"role": "user", "content": "old"}}])
    _write_jsonl(new, [{"message": {"role": "user", "content": "new"}}])
    os.utime(old, (1_000_000_000, 1_000_000_000))
    os.utime(new, (2_000_000_000, 2_000_000_000))
    docs = iter_new_raw("claude-code", since="2020-01-01T00:00:00", root=root)
    texts = [d.text for d in docs]
    assert "new" in texts and "old" not in texts


def test_missing_root_returns_empty(tmp_path: Path) -> None:
    assert iter_new_raw("claude-code", since=None, root=tmp_path / "nope") == []


def test_skips_unparseable_lines(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    f = root / "s.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('{"message":{"role":"user","content":"ok"}}\nGARBAGE\n', encoding="utf-8")
    docs = iter_new_raw("claude-code", since=None, root=root)
    assert len(docs) == 1
    assert "ok" in docs[0].text
```

- [ ] **Step 2: Run → fails**
Run: `uv run pytest tests/test_wiki_rawdoc.py -v`

- [ ] **Step 3: Implement**

```python
# src/synapse_memory/wiki/rawdoc.py
"""raw 소스 → RawDoc. P1a는 claude-code 미러 jsonl만.

각 jsonl 파일 = 한 대화 세션 = 한 RawDoc. mtime이 watermark(since) 이후인 파일만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from synapse_memory.storage.l0 import l0_root

SUPPORTED_SOURCES = ("claude-code",)


@dataclass(frozen=True)
class RawDoc:
    """ingest 단위 — 한 대화 세션의 평문 텍스트."""

    source: str
    ref: str          # "claude-code:projects/demo/sess1.jsonl"
    text: str
    mtime_iso: str    # 파일 수정 시각 (watermark 갱신용)


def default_source_root(source: str) -> Path:
    return l0_root() / "raw" / source


def _extract_text(event: dict) -> str:
    """claude-code jsonl 이벤트에서 사람이 읽는 텍스트 추출 (best-effort)."""
    msg = event.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return ""


def _file_text(path: Path) -> str:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            text = _extract_text(event)
            if text:
                lines.append(text)
    return "\n\n".join(lines)


def iter_new_raw(
    source: str,
    *,
    since: str | None,
    root: Path | None = None,
) -> list[RawDoc]:
    """source의 새 RawDoc 목록 (mtime > since). ref 정렬.

    Raises:
        ValueError: 미지원 source.
    """
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"미지원 source: {source!r}")
    base = (root or default_source_root(source)).expanduser()
    if not base.is_dir():
        return []
    since_ts = datetime.fromisoformat(since).timestamp() if since else None
    docs: list[RawDoc] = []
    for path in sorted(base.rglob("*.jsonl")):
        mtime = path.stat().st_mtime
        if since_ts is not None and mtime <= since_ts:
            continue
        text = _file_text(path)
        if not text:
            continue
        rel = path.relative_to(base).as_posix()
        docs.append(
            RawDoc(
                source=source,
                ref=f"{source}:{rel}",
                text=text,
                mtime_iso=datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
            )
        )
    return docs
```

- [ ] **Step 4: Run → pass** (4 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/rawdoc.py tests/test_wiki_rawdoc.py
git commit -m "feat(wiki): add claude-code raw reader (RawDoc, watermark-filtered)"
```

---

## Task 3: retrieval — 관련 페이지 선별 (이름매칭 + 1-hop)

**Files:**
- Create: `src/synapse_memory/wiki/retrieval.py`
- Test: `tests/test_wiki_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_retrieval.py
"""find_related_pages: 이름매칭 + 1-hop 링크 확장."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.page import WikiPage, save_page
from synapse_memory.wiki.retrieval import find_related_pages


def test_name_match_by_title_and_slug(tmp_path: Path) -> None:
    save_page(WikiPage(type="project", slug="synapse-memory", title="Synapse Memory"), vault_path=tmp_path)
    save_page(WikiPage(type="company", slug="acme", title="Acme Corp"), vault_path=tmp_path)
    hits = find_related_pages("오늘 Synapse Memory 작업했다", vault_path=tmp_path, max_pages=10)
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "acme" not in slugs


def test_one_hop_link_expansion(tmp_path: Path) -> None:
    save_page(WikiPage(type="project", slug="synapse-memory", title="Synapse Memory",
                       related=("[[rag]]",)), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    hits = find_related_pages("Synapse Memory 진행", vault_path=tmp_path, max_pages=10)
    slugs = {p.slug for p in hits}
    assert "synapse-memory" in slugs
    assert "rag" in slugs


def test_respects_max_pages(tmp_path: Path) -> None:
    for i in range(5):
        save_page(WikiPage(type="concept", slug=f"c{i}", title=f"Concept{i}"), vault_path=tmp_path)
    text = " ".join(f"Concept{i}" for i in range(5))
    hits = find_related_pages(text, vault_path=tmp_path, max_pages=2)
    assert len(hits) == 2


def test_no_match_returns_empty(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    assert find_related_pages("관련 없는 내용", vault_path=tmp_path) == []
```

- [ ] **Step 2: Run → fails**

- [ ] **Step 3: Implement**

```python
# src/synapse_memory/wiki/retrieval.py
"""관련 기존 페이지 선별 (R2 부분구현: 이름매칭 + 1-hop).

의미유사도 top-k는 P2(rag 재조준)에서 추가. 여기서는 임베딩 없이
페이지 title/slug의 본문 등장 + 그 페이지의 related 1-hop 이웃만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.page import (
    VALID_TYPES,
    WikiPage,
    extract_wikilinks,
    list_pages,
)

DEFAULT_MAX_PAGES = 12


def _all_pages(vault_path: Path | None) -> list[WikiPage]:
    pages: list[WikiPage] = []
    for t in VALID_TYPES:
        pages.extend(list_pages(t, vault_path=vault_path))
    return pages


def _find_page_by_slug(slug: str, pages: list[WikiPage]) -> WikiPage | None:
    for p in pages:
        if p.slug == slug:
            return p
    return None


def find_related_pages(
    text: str,
    *,
    vault_path: Path | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[WikiPage]:
    """본문과 관련된 기존 페이지. 이름(title/slug) 등장 매칭 + related 1-hop.

    반환 순서: 직접 매칭 먼저(등장), 그다음 1-hop 이웃. slug 기준 dedup. max_pages 상한.
    """
    haystack = text.lower()
    all_pages = _all_pages(vault_path)

    matched: list[WikiPage] = []
    matched_slugs: set[str] = set()
    for p in all_pages:
        if p.slug in matched_slugs:
            continue
        if p.title.lower() in haystack or p.slug.lower() in haystack:
            matched.append(p)
            matched_slugs.add(p.slug)

    neighbors: list[WikiPage] = []
    for p in matched:
        for link in p.related:
            for target in (extract_wikilinks(link) or [link.strip("[]")]):
                if target in matched_slugs:
                    continue
                neighbor = _find_page_by_slug(target, all_pages)
                if neighbor is not None:
                    neighbors.append(neighbor)
                    matched_slugs.add(target)

    return (matched + neighbors)[:max_pages]
```

- [ ] **Step 4: Run → pass** (4 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/retrieval.py tests/test_wiki_retrieval.py
git commit -m "feat(wiki): add related-page retrieval (name-match + 1-hop)"
```

---

## Task 4: integration — 스키마 + 프롬프트 + ops 파싱

**Files:**
- Create: `src/synapse_memory/wiki/integration.py`
- Test: `tests/test_wiki_integration.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run → fails**

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run → pass** (5 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/integration.py tests/test_wiki_integration.py
git commit -m "feat(wiki): add integration schema, prompt builder, ops parser"
```

---

## Task 5: apply — ops 적용 + 양방향 링크

**Files:**
- Create: `src/synapse_memory/wiki/apply.py`
- Test: `tests/test_wiki_apply.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_apply.py
"""apply_ops: save_page + 양방향 링크 + updated 스탬프."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.apply import apply_ops
from synapse_memory.wiki.integration import PageOp
from synapse_memory.wiki.page import WikiPage, load_page, save_page


def test_apply_creates_page_and_stamps_updated(tmp_path: Path) -> None:
    op = PageOp(op="create", page=WikiPage(type="concept", slug="rag", title="RAG", body="b"))
    written = apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    assert written == ["rag"]
    saved = load_page("concept", "rag", vault_path=tmp_path)
    assert saved.body.strip() == "b"
    assert saved.updated == "2026-06-14"


def test_apply_adds_back_link(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="rag", title="RAG"), vault_path=tmp_path)
    op = PageOp(op="create", page=WikiPage(type="project", slug="synapse-memory",
                title="Synapse Memory", related=("[[rag]]",), body="b"))
    apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    rag = load_page("concept", "rag", vault_path=tmp_path)
    assert "[[synapse-memory]]" in rag.related


def test_apply_skips_backlink_when_target_missing(tmp_path: Path) -> None:
    op = PageOp(op="create", page=WikiPage(type="project", slug="p", title="P",
                related=("[[ghost]]",), body="b"))
    written = apply_ops([op], vault_path=tmp_path, today="2026-06-14")
    assert written == ["p"]
```

- [ ] **Step 2: Run → fails**

- [ ] **Step 3: Implement**

```python
# src/synapse_memory/wiki/apply.py
"""PageOp 목록을 vault에 적용 — save_page + 양방향 링크 보강.

끊긴 링크 전체 점검(lint)은 P4. 여기서는 방금 추가한 related의 즉시 역링크만.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from synapse_memory.wiki.integration import PageOp
from synapse_memory.wiki.page import (
    WikiPage,
    extract_wikilinks,
    load_page,
    save_page,
    with_related,
)


def _link_targets(page: WikiPage) -> list[str]:
    targets: list[str] = []
    for link in page.related:
        targets.extend(extract_wikilinks(link) or [link.strip("[]")])
    return targets


def _add_back_links(page: WikiPage, *, vault_path: Path | None) -> None:
    """page가 가리키는 각 대상에 page로의 역링크 추가 (대상 존재 시만)."""
    back = f"[[{page.slug}]]"
    for target_slug in _link_targets(page):
        for ptype in ("project", "company", "person", "concept", "profile"):
            try:
                target = load_page(ptype, target_slug, vault_path=vault_path)
            except (FileNotFoundError, ValueError):
                continue
            if back not in target.related:
                save_page(with_related(target, back), vault_path=vault_path)
            break


def apply_ops(
    ops: list[PageOp],
    *,
    vault_path: Path | None = None,
    today: str | None = None,
) -> list[str]:
    """ops 적용. 반환: 기록된 페이지 slug 목록 (순서 보존)."""
    stamp = today or date.today().isoformat()
    written: list[str] = []
    for op in ops:
        page = replace(op.page, updated=stamp)
        save_page(page, vault_path=vault_path)
        written.append(page.slug)
        _add_back_links(page, vault_path=vault_path)
    return written
```

- [ ] **Step 4: Run → pass** (3 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/apply.py tests/test_wiki_apply.py
git commit -m "feat(wiki): add apply_ops with updated stamp + bidirectional links"
```

---

## Task 6: log — log.md 시간순 기록

**Files:**
- Create: `src/synapse_memory/wiki/log.py`
- Test: `tests/test_wiki_log.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_log.py
"""log.md append (시간순, grep 친화)."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.log import append_log, log_path


def test_log_path_is_vault_root(tmp_path: Path) -> None:
    assert log_path(vault_path=tmp_path) == tmp_path / "log.md"


def test_append_creates_and_appends(tmp_path: Path) -> None:
    append_log("ingest claude-code: 2 pages (synapse-memory, rag)",
               vault_path=tmp_path, when="2026-06-14T10:00:00")
    append_log("ingest claude-code: 1 page (acme)",
               vault_path=tmp_path, when="2026-06-14T11:00:00")
    text = (tmp_path / "log.md").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2
    assert "2026-06-14T10:00:00" in lines[0]
    assert "synapse-memory" in lines[0]
    assert "acme" in lines[1]
```

- [ ] **Step 2: Run → fails**

- [ ] **Step 3: Implement**

```python
# src/synapse_memory/wiki/log.py
"""vault 루트 log.md — ingest/lint 변경의 시간순 1줄 기록 (grep 친화).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path

LOG_FILENAME = "log.md"
_HEADER = "# Wiki Change Log\n\n"


def log_path(*, vault_path: Path | None = None) -> Path:
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / LOG_FILENAME


def append_log(message: str, *, vault_path: Path | None = None, when: str | None = None) -> Path:
    """log.md에 '- <iso> <message>' 한 줄 추가. 파일/헤더 없으면 생성."""
    path = log_path(vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = when or datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"- {stamp} {message}\n"
    if not path.is_file():
        path.write_text(_HEADER + line, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return path
```

- [ ] **Step 4: Run → pass** (2 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/log.py tests/test_wiki_log.py
git commit -m "feat(wiki): add log.md append helper"
```

---

## Task 7: ingest — 오케스트레이터

**Files:**
- Create: `src/synapse_memory/wiki/ingest.py`
- Modify: `src/synapse_memory/wiki/__init__.py`
- Test: `tests/test_wiki_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_ingest.py
"""ingest_source 오케스트레이션 (LLM은 monkeypatch)."""
from __future__ import annotations

import json
from pathlib import Path

import synapse_memory.wiki.ingest as ingest_mod
from synapse_memory.wiki.ingest import ingest_source
from synapse_memory.wiki.page import load_page
from synapse_memory.wiki.watermark import load_watermark


def _write_session(root: Path, name: str, user_text: str) -> None:
    f = root / f"{name}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps({"message": {"role": "user", "content": user_text}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _fake_complete_structured(ops_payload):
    def _fn(prompt, *, system=None, model=None, json_schema=None, env=None, timeout=120, **kw):
        return ops_payload
    return _fn


def test_ingest_creates_page_and_updates_watermark(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "sess1", "Synapse Memory 프로젝트 시작")
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured",
        _fake_complete_structured({"operations": [
            {"op": "create", "type": "project", "slug": "synapse-memory",
             "title": "Synapse Memory", "body": "프로젝트 본문", "related": [], "sources": []}]}))
    result = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                           watermark_path=state, ai_env=None, today="2026-06-14")
    assert result.docs_processed == 1
    assert "synapse-memory" in result.pages_written
    assert load_page("project", "synapse-memory", vault_path=tmp_path).title == "Synapse Memory"
    again = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                          watermark_path=state, ai_env=None, today="2026-06-14")
    assert again.docs_processed == 0


def test_ingest_dry_run_writes_nothing(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw" / "claude-code"
    _write_session(raw_root, "s", "RAG 개념 정리")
    state = tmp_path / "state.json"
    monkeypatch.setattr(ingest_mod.ai_api, "complete_structured",
        _fake_complete_structured({"operations": [
            {"op": "create", "type": "concept", "slug": "rag", "title": "RAG", "body": "b"}]}))
    result = ingest_source("claude-code", vault_path=tmp_path, raw_root=raw_root,
                           watermark_path=state, ai_env=None, dry_run=True, today="2026-06-14")
    assert result.pages_written == []
    assert not (tmp_path / "Concepts" / "rag.md").exists()
    assert load_watermark("claude-code", path=state) is None
```

- [ ] **Step 2: Run → fails**

- [ ] **Step 3: Implement**

```python
# src/synapse_memory/wiki/ingest.py
"""ingest 오케스트레이터 — raw → 관련페이지 → 통합 → 적용 + 로그 + watermark.

엔진은 ai_api.complete_structured(json_schema=INTEGRATION_SCHEMA). redaction 없음(D4).

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from synapse_memory.llm import ai_api
from synapse_memory.wiki.apply import apply_ops
from synapse_memory.wiki.integration import (
    INTEGRATION_SCHEMA,
    INTEGRATION_SYSTEM,
    PageOp,
    build_integration_prompt,
    parse_ops,
)
from synapse_memory.wiki.log import append_log
from synapse_memory.wiki.rawdoc import iter_new_raw
from synapse_memory.wiki.retrieval import find_related_pages
from synapse_memory.wiki.watermark import load_watermark, save_watermark


@dataclass
class IngestResult:
    source: str
    docs_processed: int = 0
    pages_written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _stamp_sources(ops: list[PageOp], ref: str) -> list[PageOp]:
    out: list[PageOp] = []
    for op in ops:
        if ref not in op.page.sources:
            page = replace(op.page, sources=(*op.page.sources, ref))
        else:
            page = op.page
        out.append(replace(op, page=page))
    return out


def ingest_source(
    source: str,
    *,
    vault_path: Path | None = None,
    raw_root: Path | None = None,
    watermark_path: Path | None = None,
    ai_env: object | None = None,
    model: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    today: str | None = None,
) -> IngestResult:
    """source의 새 RawDoc을 ingest. dry_run이면 적용/watermark/로그 생략."""
    since = load_watermark(source, path=watermark_path)
    docs = iter_new_raw(source, since=since, root=raw_root)
    if limit is not None:
        docs = docs[:limit]

    result = IngestResult(source=source)
    max_mtime = since
    for doc in docs:
        result.docs_processed += 1
        try:
            related = find_related_pages(doc.text, vault_path=vault_path)
            prompt = build_integration_prompt(doc.text, related)
            payload = ai_api.complete_structured(
                prompt, system=INTEGRATION_SYSTEM, model=model,
                json_schema=INTEGRATION_SCHEMA, env=ai_env, timeout=120,
            )
            ops = _stamp_sources(parse_ops(payload), doc.ref)
            if dry_run:
                result.pages_written.extend(op.page.slug for op in ops)
                continue
            written = apply_ops(ops, vault_path=vault_path, today=today)
            result.pages_written.extend(written)
            if written:
                append_log(
                    f"ingest {source}: {len(written)} pages "
                    f"({', '.join(written)}) from {doc.ref}",
                    vault_path=vault_path,
                )
        except Exception as exc:  # noqa: BLE001 — 한 doc 실패가 전체를 막지 않음
            result.errors.append(f"{doc.ref}: {exc}")
        if max_mtime is None or doc.mtime_iso > max_mtime:
            max_mtime = doc.mtime_iso

    if not dry_run and max_mtime and max_mtime != since:
        save_watermark(source, max_mtime, path=watermark_path)
    return result
```

`wiki/__init__.py`에 추가 (import + `__all__`): `IngestResult`, `ingest_source`.

- [ ] **Step 4: Run → pass** (2 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/wiki/ingest.py src/synapse_memory/wiki/__init__.py tests/test_wiki_ingest.py
git commit -m "feat(wiki): add ingest orchestrator (raw->integrate->apply, dry-run, watermark)"
```

---

## Task 8: CLI — `ingest` 서브커맨드

**Files:**
- Modify: `src/synapse_memory/cli.py`
- Test: `tests/test_cli_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_ingest.py
"""ingest CLI 서브커맨드 — 인자 파싱 + 오케스트레이터 위임."""
from __future__ import annotations

import synapse_memory.cli as cli
from synapse_memory.wiki.ingest import IngestResult


def test_ingest_now_invokes_engine(monkeypatch, capsys) -> None:
    captured = {}

    def fake_ingest(source, **kwargs):
        captured["source"] = source
        captured["dry_run"] = kwargs.get("dry_run")
        return IngestResult(source=source, docs_processed=2, pages_written=["a", "b"])

    monkeypatch.setattr(cli, "ingest_source", fake_ingest)
    rc = cli.main(["ingest", "--now", "--source", "claude-code"])
    assert rc == 0
    assert captured["source"] == "claude-code"
    assert "2" in capsys.readouterr().out


def test_ingest_dry_run_flag(monkeypatch) -> None:
    captured = {}

    def fake_ingest(source, **kwargs):
        captured["dry_run"] = kwargs.get("dry_run")
        return IngestResult(source=source, docs_processed=0)

    monkeypatch.setattr(cli, "ingest_source", fake_ingest)
    cli.main(["ingest", "--now", "--dry-run"])
    assert captured["dry_run"] is True
```

> cli.py는 모듈 상단에서 `from synapse_memory.wiki.ingest import ingest_source`를 import해야 monkeypatch가 `cli.ingest_source`를 잡는다.

- [ ] **Step 2: Run → fails**

- [ ] **Step 3: Implement**

cli.py 상단 import 추가: `from synapse_memory.wiki.ingest import ingest_source`

`build_parser()`의 서브파서 등록부(예: `daily` 인근)에 추가:
```python
    p_ingest = sub.add_parser("ingest", help="wiki ingest 엔진 (raw 대화 → wiki 통합)")
    p_ingest.add_argument("--now", action="store_true", help="즉시 1회 ingest")
    p_ingest.add_argument("--source", default="claude-code", choices=["claude-code"],
                          help="ingest 소스 (P1a: claude-code)")
    p_ingest.add_argument("--dry-run", action="store_true", help="적용 없이 결과만 표시")
    p_ingest.add_argument("--limit", type=int, default=None, help="처리할 최대 doc 수")
    p_ingest.set_defaults(func=cmd_ingest)
```

cmd_ingest 함수 추가(기존 cmd_* 스타일):
```python
def cmd_ingest(args: argparse.Namespace) -> int:
    """wiki ingest 엔진 1회 실행."""
    dry = bool(getattr(args, "dry_run", False))
    result = ingest_source(args.source, dry_run=dry, limit=args.limit)
    label = "(dry-run) " if dry else ""
    print(f"{label}ingest {result.source}: docs={result.docs_processed}, "
          f"pages={len(result.pages_written)}")
    if result.pages_written:
        print("  written: " + ", ".join(result.pages_written))
    if result.errors:
        print(f"  errors: {len(result.errors)}")
        for e in result.errors:
            print(f"    - {e}")
    return 0
```

- [ ] **Step 4: Run → pass** (2 passed)
- [ ] **Step 5: Commit**
```bash
git add src/synapse_memory/cli.py tests/test_cli_ingest.py
git commit -m "feat(cli): add 'ingest --now' subcommand"
```

---

## Task 9: 전체 회귀 + lint

**Files:** (검증 전용)

- [ ] **Step 1:** `uv run pytest -q` → 전체 통과, 회귀 없음.
- [ ] **Step 2:** `uv run ruff check src/synapse_memory/wiki src/synapse_memory/cli.py tests/test_wiki_*.py tests/test_cli_ingest.py` → clean.
- [ ] **Step 3:** lint 수정 있으면 `git add -A && git commit -m "chore(wiki): satisfy lint for ingest engine"`.

---

## Self-Review (작성자 체크리스트 결과)

- **Spec coverage:** spec 019 §4 INGEST(raw→관련페이지→통합 ops→적용+log) + R2(이름매칭+1-hop; 의미유사도는 P2 명시) + R5(watermark 증분) + §6 provenance(sources에 doc.ref). 트리거(P3)/lint(P4)/멀티소스/의미인덱싱(P2)은 범위 메모에 명시 제외.
- **Placeholder scan:** 모든 태스크에 구체 test/impl + 명령 + 기대결과. placeholder 없음.
- **Type consistency:** `RawDoc(source/ref/text/mtime_iso)`, `PageOp(op, page)`, `IngestResult(source/docs_processed/pages_written/errors)`, `ingest_source(source, *, vault_path, raw_root, watermark_path, ai_env, model, dry_run, limit, today)`, `find_related_pages(text, *, vault_path, max_pages)`, `apply_ops(ops, *, vault_path, today)`, `parse_ops(payload)->list[PageOp]`가 전 태스크 일관. `ai_api.complete_structured` 시그니처는 Explore 확인치와 일치.
