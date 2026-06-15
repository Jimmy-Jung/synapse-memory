# P0 — Wiki Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synapse Memory v2의 기반 데이터 계층 — 통합형 `WikiPage` 모델, 새 vault 폴더/유지엔진 config, vault 루트 `SCHEMA.md` 스캐폴딩 — 을 순수 추가(additive)로 구축한다.

**Architecture:** 기존 `cards/project.py`의 "dataclass + frontmatter serialize/parse + 디스크 I/O" 패턴을 단일 `wiki/page.py`로 일반화한다. 6개 페이지 타입(project/company/person/concept/profile/insight)을 하나의 frozen dataclass로 표현하고, 타입→폴더 매핑을 config에서 가져온다. apfel·redaction 삭제는 호출처가 P1/P2에서 재작성되므로 **이 플랜 범위 밖**(곧 버려질 코드를 손대는 낭비 방지).

**Tech Stack:** Python 3.11+, `dataclasses`(frozen + `replace`), `pyyaml`, `pytest`. 기존 `synapse_memory.config`, `synapse_memory.folders.year_month_path`, `synapse_memory.collectors.obsidian.mirror.get_vault_path` 재사용.

---

## 범위 메모 (Scope notes)

- **포함**: `wiki/page.py`(모델+I/O+링크 헬퍼), config 추가(`maintenance`, `vault_folders.wiki`), `wiki/schema.py`(SCHEMA.md 템플릿+writer).
- **제외 (의도적)**: apfel/redaction 삭제(P1/P2 동승), ingest 엔진(P1), 검색/환원(P2), watch 데몬(P3), lint(P4), 초기 백필(P5).
- **불변성**: `WikiPage`는 frozen dataclass + tuple 필드. 갱신은 `dataclasses.replace`로 새 객체 반환(전역 coding-style 규칙 준수).
- **검증**: `parse_page`/`page_dir`는 알 수 없는 `type`에 `ValueError`로 fail-fast.

---

## File Structure

- Create: `src/synapse_memory/wiki/__init__.py` — 패키지 export.
- Create: `src/synapse_memory/wiki/page.py` — `WikiPage` 모델, serialize/parse, slugify, page_dir/page_path, load/save/list, `extract_wikilinks`, `with_related`.
- Create: `src/synapse_memory/wiki/schema.py` — `SCHEMA_TEMPLATE` 상수, `schema_path`, `write_schema`, `ensure_schema`.
- Modify: `src/synapse_memory/config.py` — `VaultWikiFoldersConfig` 추가 + `VaultFoldersConfig.wiki` 필드, `MaintenanceConfig` 추가 + `SynapseConfig.maintenance` 필드.
- Test: `tests/test_wiki_page.py`, `tests/test_wiki_schema.py`, `tests/test_config_maintenance.py`.

각 파일 1책임: `page.py`=페이지 모델·I/O, `schema.py`=스키마 문서 생성, config 변경=설정 계약.

---

## Task 1: config — 유지엔진 + wiki 폴더 설정

**Files:**
- Modify: `src/synapse_memory/config.py` (VaultFoldersConfig 위 `124`행 근처, SynapseConfig `220`행 근처)
- Test: `tests/test_config_maintenance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_maintenance.py
"""maintenance + vault_folders.wiki 설정 기본값/override 검증."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.config import get_config


def test_maintenance_defaults() -> None:
    cfg = get_config(refresh=True)
    assert cfg.maintenance.engine == "claude"
    assert cfg.maintenance.idle_minutes == 3


def test_wiki_folder_defaults() -> None:
    cfg = get_config(refresh=True)
    w = cfg.vault_folders.wiki
    assert w.projects == "Entities/Projects"
    assert w.companies == "Entities/Companies"
    assert w.people == "Entities/People"
    assert w.concepts == "Concepts"
    assert w.profile == "Profile"
    assert w.insights == "Insights"


def test_maintenance_override_from_yaml(tmp_path: Path, monkeypatch) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "maintenance:\n  engine: codex\n  idle_minutes: 5\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNAPSE_CONFIG_PATH", str(cfg_file))
    cfg = get_config(refresh=True)
    assert cfg.maintenance.engine == "codex"
    assert cfg.maintenance.idle_minutes == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_maintenance.py -v`
Expected: FAIL — `AttributeError: 'SynapseConfig' object has no attribute 'maintenance'` (and `wiki`).

> 참고: `get_config`가 `SYNAPSE_CONFIG_PATH` 환경변수를 읽는지 먼저 확인할 것(`config.py`의 `DEFAULT_CONFIG_PATH`/loader 부근). 읽지 않으면 테스트는 `monkeypatch`로 loader가 보는 경로를 맞춰 수정한다(기존 `tests/test_config.py` 패턴 따름).

- [ ] **Step 3: Write minimal implementation**

`config.py`에 `VaultReferenceFoldersConfig` 정의들 근처(`124`행 이전)에 추가:

```python
@dataclass
class VaultWikiFoldersConfig:
    """v2 wiki 페이지 폴더 — vault root 기준 상대 경로.

    Karpathy LLM-wiki 패턴의 entity/concept/profile/insight 페이지 저장 위치.
    """

    projects: str = "Entities/Projects"
    companies: str = "Entities/Companies"
    people: str = "Entities/People"
    concepts: str = "Concepts"
    profile: str = "Profile"
    insights: str = "Insights"
```

`VaultFoldersConfig`(`125`행) 에 필드 추가 (`system` 필드 아래):

```python
    wiki: VaultWikiFoldersConfig = field(default_factory=VaultWikiFoldersConfig)
```

`AutomationConfig`(`195`행) 근처에 추가:

```python
@dataclass
class MaintenanceConfig:
    """v2 wiki 자동 유지엔진 설정.

    engine: wiki 통합/lint를 수행할 CLI ("claude" | "codex"). 설치 시 선택.
    idle_minutes: watch 데몬이 "대화 종료"로 간주하는 무변경 임계값(분).
    """

    engine: str = "claude"
    idle_minutes: int = 3
```

`SynapseConfig`(`220`행) 에 필드 추가 (`automation` 필드 아래):

```python
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_maintenance.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify no regression in existing config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (기존 직렬화/flatten 테스트가 새 필드와 함께 통과).

- [ ] **Step 6: Commit**

```bash
git add src/synapse_memory/config.py tests/test_config_maintenance.py
git commit -m "feat(config): add maintenance engine + wiki folder settings"
```

---

## Task 2: WikiPage 모델 + serialize/parse

**Files:**
- Create: `src/synapse_memory/wiki/__init__.py`
- Create: `src/synapse_memory/wiki/page.py`
- Test: `tests/test_wiki_page.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_page.py
"""WikiPage 모델 round-trip + 검증."""
from __future__ import annotations

import pytest

from synapse_memory.wiki.page import (
    WikiPage,
    parse_page,
    serialize_page,
)


def test_serialize_parse_round_trip() -> None:
    page = WikiPage(
        type="project",
        slug="synapse-memory",
        title="Synapse Memory",
        related=("[[obsidian]]", "[[rag]]"),
        sources=("claude_code:2026-06-14/sess-abc",),
        updated="2026-06-14",
        status="active",
        body="# Synapse Memory\n\n세컨드브레인 도구.\n",
    )
    text = serialize_page(page)
    assert text.startswith("---\n")
    restored = parse_page(text)
    assert restored == page


def test_parse_requires_frontmatter() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_page("frontmatter 없는 본문")


def test_parse_rejects_unknown_type() -> None:
    text = "---\ntype: wibble\nslug: x\ntitle: X\n---\n\nbody"
    with pytest.raises(ValueError, match="type"):
        parse_page(text)


def test_parse_requires_slug_and_title() -> None:
    text = "---\ntype: concept\nslug: x\n---\n\nbody"
    with pytest.raises(ValueError, match="title"):
        parse_page(text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wiki_page.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'synapse_memory.wiki'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/synapse_memory/wiki/__init__.py
"""v2 LLM-maintained wiki 페이지 계층."""
from __future__ import annotations

from synapse_memory.wiki.page import (
    VALID_TYPES,
    WikiPage,
    extract_wikilinks,
    list_pages,
    load_page,
    page_dir,
    page_path,
    parse_page,
    save_page,
    serialize_page,
    slugify,
    with_related,
)

__all__ = [
    "VALID_TYPES",
    "WikiPage",
    "extract_wikilinks",
    "list_pages",
    "load_page",
    "page_dir",
    "page_path",
    "parse_page",
    "save_page",
    "serialize_page",
    "slugify",
    "with_related",
]
```

```python
# src/synapse_memory/wiki/page.py
"""WikiPage — 통합형 wiki 페이지 (yaml frontmatter + markdown body).

6개 타입(project/company/person/concept/profile/insight)을 단일 frozen
dataclass로 표현. cards/project.py 패턴을 일반화. 사람이 Obsidian에서 직접
편집 가능하고 Python에서도 parse/serialize 가능.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config
from synapse_memory.folders import year_month_path

FRONTMATTER_DELIMITER = "---"
VALID_TYPES: tuple[str, ...] = (
    "project",
    "company",
    "person",
    "concept",
    "profile",
    "insight",
)

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)
_SLUG_RE = re.compile(r"[^a-zA-Z0-9가-힣\-_]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass(frozen=True)
class WikiPage:
    """LLM이 소유·유지하는 단일 지식 페이지.

    불변(frozen). 갱신은 dataclasses.replace 또는 with_related로 새 객체 생성.
    """

    type: str
    slug: str
    title: str
    related: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    updated: str = ""
    status: str = "active"
    body: str = ""

    @property
    def filename(self) -> str:
        return f"{self.slug}.md"


def _frontmatter_dict(page: WikiPage) -> dict[str, Any]:
    """body 제외 필드를 dict로. 빈 컬렉션은 생략 — 깔끔한 yaml."""
    d: dict[str, Any] = {
        "type": page.type,
        "slug": page.slug,
        "title": page.title,
    }
    if page.related:
        d["related"] = list(page.related)
    if page.sources:
        d["sources"] = list(page.sources)
    if page.updated:
        d["updated"] = page.updated
    d["status"] = page.status
    d["tags"] = ["node/wiki", f"node/{page.type}"]
    return d


def serialize_page(page: WikiPage) -> str:
    """WikiPage → markdown 문자열 (yaml frontmatter + body)."""
    if page.type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page.type!r}")
    fm = _frontmatter_dict(page)
    yaml_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    body = page.body.lstrip("\n")
    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}"


def parse_page(text: str) -> WikiPage:
    """markdown 문자열 → WikiPage.

    Raises:
        ValueError: frontmatter 없음 / type 미지원 / slug·title 누락 / yaml 오류.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("frontmatter (--- ... ---) 없음")
    try:
        meta = yaml.safe_load(m.group("yaml")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")

    page_type = meta.get("type")
    if page_type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    slug = meta.get("slug")
    title = meta.get("title")
    if not slug:
        raise ValueError("필수 필드 누락: slug")
    if not title:
        raise ValueError("필수 필드 누락: title")

    return WikiPage(
        type=str(page_type),
        slug=str(slug),
        title=str(title),
        related=tuple(str(x) for x in (meta.get("related") or [])),
        sources=tuple(str(x) for x in (meta.get("sources") or [])),
        updated=str(meta.get("updated", "")),
        status=str(meta.get("status", "active")),
        body=m.group("body"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_wiki_page.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/synapse_memory/wiki/__init__.py src/synapse_memory/wiki/page.py tests/test_wiki_page.py
git commit -m "feat(wiki): add WikiPage model with frontmatter serialize/parse"
```

---

## Task 3: slugify + 디스크 I/O (page_dir/page_path/save/load/list)

**Files:**
- Modify: `src/synapse_memory/wiki/page.py` (Task 2 끝에 함수 추가)
- Test: `tests/test_wiki_page.py` (테스트 추가)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_page.py 에 추가
from pathlib import Path

from synapse_memory.wiki.page import (
    list_pages,
    load_page,
    page_dir,
    save_page,
    slugify,
)


def test_slugify_korean_and_spaces() -> None:
    assert slugify("Synapse Memory") == "synapse-memory"
    assert slugify("이력서 작성") == "이력서-작성"
    assert slugify("  !!  ") == "untitled"


def test_page_dir_by_type(tmp_path: Path) -> None:
    assert page_dir("project", vault_path=tmp_path) == tmp_path / "Entities/Projects"
    assert page_dir("company", vault_path=tmp_path) == tmp_path / "Entities/Companies"
    assert page_dir("person", vault_path=tmp_path) == tmp_path / "Entities/People"
    assert page_dir("concept", vault_path=tmp_path) == tmp_path / "Concepts"
    assert page_dir("profile", vault_path=tmp_path) == tmp_path / "Profile"


def test_page_dir_insight_uses_year_month(tmp_path: Path) -> None:
    import datetime

    d = page_dir("insight", vault_path=tmp_path, when=datetime.date(2026, 6, 14))
    assert d == tmp_path / "Insights" / "2026" / "06"


def test_page_dir_rejects_unknown_type(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="type"):
        page_dir("wibble", vault_path=tmp_path)


def test_save_load_round_trip(tmp_path: Path) -> None:
    page = WikiPage(
        type="concept",
        slug="rag",
        title="RAG",
        body="# RAG\n검색 증강 생성.\n",
    )
    path = save_page(page, vault_path=tmp_path)
    assert path == tmp_path / "Concepts" / "rag.md"
    assert path.is_file()
    loaded = load_page("concept", "rag", vault_path=tmp_path)
    assert loaded == page


def test_list_pages_sorted_and_skips_bad(tmp_path: Path) -> None:
    save_page(WikiPage(type="concept", slug="zeta", title="Zeta"), vault_path=tmp_path)
    save_page(WikiPage(type="concept", slug="alpha", title="Alpha"), vault_path=tmp_path)
    (tmp_path / "Concepts" / "broken.md").write_text("no frontmatter", encoding="utf-8")
    pages = list_pages("concept", vault_path=tmp_path)
    assert [p.slug for p in pages] == ["alpha", "zeta"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wiki_page.py -v`
Expected: FAIL — `ImportError: cannot import name 'page_dir'`.

- [ ] **Step 3: Write minimal implementation**

`wiki/page.py` 끝에 추가:

```python
# ---------------------------------------------------------------------------
# slug + 디스크 I/O
# ---------------------------------------------------------------------------

_TYPE_FOLDER_ATTR = {
    "project": "projects",
    "company": "companies",
    "person": "people",
    "concept": "concepts",
    "profile": "profile",
}


def slugify(name: str) -> str:
    """display name → file-safe slug. 한국어 음절 보존, 공백 → ``-``."""
    s = name.strip().replace(" ", "-").lower()
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def page_dir(
    page_type: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> Path:
    """페이지 타입별 저장 디렉토리. insight는 연/월 하위폴더 사용."""
    if page_type not in VALID_TYPES:
        raise ValueError(f"알 수 없는 type: {page_type!r}")
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    wiki = get_config().vault_folders.wiki
    if page_type == "insight":
        return year_month_path(vault / wiki.insights, when or date.today())
    sub = getattr(wiki, _TYPE_FOLDER_ATTR[page_type])
    return vault / sub


def _insight_when(page: WikiPage) -> date:
    """insight 페이지의 updated(YYYY-MM-DD)로 연/월 폴더 결정. 없으면 today."""
    if page.updated:
        try:
            return date.fromisoformat(page.updated)
        except ValueError:
            pass
    return date.today()


def page_path(page: WikiPage, *, vault_path: Path | None = None) -> Path:
    """페이지의 디스크 경로."""
    when = _insight_when(page) if page.type == "insight" else None
    return page_dir(page.type, vault_path=vault_path, when=when) / page.filename


def save_page(page: WikiPage, *, vault_path: Path | None = None) -> Path:
    """WikiPage → vault 디스크. 디렉토리 자동 생성. 기존 파일 덮어씀."""
    path = page_path(page, vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_page(page), encoding="utf-8")
    return path


def load_page(
    page_type: str,
    slug: str,
    *,
    vault_path: Path | None = None,
    when: date | None = None,
) -> WikiPage:
    """타입+slug로 페이지 로드.

    Raises:
        FileNotFoundError: 해당 페이지 없음.
    """
    path = page_dir(page_type, vault_path=vault_path, when=when) / f"{slug}.md"
    if not path.is_file():
        raise FileNotFoundError(f"wiki 페이지 없음: {path}")
    return parse_page(path.read_text(encoding="utf-8"))


def list_pages(
    page_type: str,
    *,
    vault_path: Path | None = None,
) -> list[WikiPage]:
    """해당 타입 모든 페이지 로드 (parse 실패는 skip). slug 알파벳순.

    insight는 연/월 하위폴더를 재귀 탐색한다.
    """
    if page_type == "insight":
        base = (
            (vault_path or get_vault_path()).expanduser().resolve()
            / get_config().vault_folders.wiki.insights
        )
    else:
        base = page_dir(page_type, vault_path=vault_path)
    if not base.is_dir():
        return []
    pages: list[WikiPage] = []
    for p in sorted(base.rglob("*.md")):
        try:
            pages.append(parse_page(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(pages, key=lambda pg: pg.slug)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_wiki_page.py -v`
Expected: PASS (전체 통과).

- [ ] **Step 5: Commit**

```bash
git add src/synapse_memory/wiki/page.py tests/test_wiki_page.py
git commit -m "feat(wiki): add slugify + disk I/O (page_dir/save/load/list)"
```

---

## Task 4: 링크 헬퍼 (extract_wikilinks + with_related)

**Files:**
- Modify: `src/synapse_memory/wiki/page.py`
- Test: `tests/test_wiki_page.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_page.py 에 추가
from synapse_memory.wiki.page import extract_wikilinks, with_related


def test_extract_wikilinks() -> None:
    body = "관련: [[rag]] 와 [[obsidian]], 그리고 또 [[rag]].\n"
    assert extract_wikilinks(body) == ["rag", "obsidian"]


def test_extract_wikilinks_empty() -> None:
    assert extract_wikilinks("링크 없음") == []


def test_with_related_adds_and_dedupes() -> None:
    page = WikiPage(type="concept", slug="rag", title="RAG", related=("[[obsidian]]",))
    updated = with_related(page, "[[bm25]]")
    assert updated.related == ("[[obsidian]]", "[[bm25]]")
    # 원본 불변 확인
    assert page.related == ("[[obsidian]]",)
    # 중복 추가는 무시
    assert with_related(updated, "[[obsidian]]").related == ("[[obsidian]]", "[[bm25]]")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wiki_page.py -k "wikilink or related" -v`
Expected: FAIL — `ImportError: cannot import name 'extract_wikilinks'`.

- [ ] **Step 3: Write minimal implementation**

`wiki/page.py` 끝에 추가:

```python
# ---------------------------------------------------------------------------
# 링크 그래프 헬퍼
# ---------------------------------------------------------------------------


def extract_wikilinks(text: str) -> list[str]:
    """본문에서 [[링크]] 대상을 등장 순서로, 중복 제거해 반환."""
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.findall(text):
        target = match.strip()
        if target and target not in seen:
            seen[target] = None
    return list(seen.keys())


def with_related(page: WikiPage, link: str) -> WikiPage:
    """related에 link를 추가한 새 WikiPage 반환 (불변, 중복 무시).

    link는 "[[slug]]" 형식을 권장.
    """
    if link in page.related:
        return page
    return replace(page, related=(*page.related, link))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_wiki_page.py -v`
Expected: PASS (전체 통과).

- [ ] **Step 5: Commit**

```bash
git add src/synapse_memory/wiki/page.py tests/test_wiki_page.py
git commit -m "feat(wiki): add wikilink extraction + immutable with_related helper"
```

---

## Task 5: SCHEMA.md 템플릿 + writer

**Files:**
- Create: `src/synapse_memory/wiki/schema.py`
- Modify: `src/synapse_memory/wiki/__init__.py` (export 추가)
- Test: `tests/test_wiki_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wiki_schema.py
"""SCHEMA.md 생성 검증."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.schema import (
    SCHEMA_FILENAME,
    ensure_schema,
    schema_path,
    write_schema,
)


def test_schema_path_is_vault_root(tmp_path: Path) -> None:
    assert schema_path(vault_path=tmp_path) == tmp_path / SCHEMA_FILENAME


def test_write_schema_creates_file(tmp_path: Path) -> None:
    path = write_schema(vault_path=tmp_path)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    # 핵심 작업 지침 키워드가 포함돼야 함
    assert "ingest" in text.lower()
    assert "lint" in text.lower()
    assert "[[" in text  # 위키링크 규약 설명


def test_ensure_schema_does_not_overwrite(tmp_path: Path) -> None:
    path = write_schema(vault_path=tmp_path)
    path.write_text("USER EDITED", encoding="utf-8")
    returned = ensure_schema(vault_path=tmp_path)
    assert returned == path
    assert path.read_text(encoding="utf-8") == "USER EDITED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wiki_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'synapse_memory.wiki.schema'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/synapse_memory/wiki/schema.py
"""SCHEMA.md — wiki의 "CLAUDE.md". vault 루트에 위치.

페이지 분류·작성 규칙·링크 규약 + ingest/query/lint 작업 지침을 한 파일에 정의한다.
어떤 에이전트(claude/codex/cursor)든 이 파일을 읽으면 wiki 유지법을 알게 된다.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path

SCHEMA_FILENAME = "SCHEMA.md"

SCHEMA_TEMPLATE = """\
# Synapse Memory — Wiki SCHEMA

이 vault는 LLM이 유지하는 개인 wiki(세컨드브레인)입니다. 어떤 에이전트든 이 파일을
읽고 아래 규약대로 페이지를 작성·갱신·정리합니다. 사람이 직접 편집해도 됩니다.

## 페이지 타입

| type | 폴더 | 용도 |
|------|------|------|
| project | `Entities/Projects/` | 프로젝트 진실원본 (이력서·면접 자산) |
| company | `Entities/Companies/` | 회사·지원내역·JD |
| person  | `Entities/People/`    | 인물 |
| concept | `Concepts/`           | 기술·의사결정원칙·반복 주제 |
| profile | `Profile/`            | 나에 대한 사실·선호·결정패턴 |
| insight | `Insights/<yyyy>/<mm>/`| 질의 답변 write-back |

## frontmatter 규약

```yaml
---
type: project|company|person|concept|profile|insight
slug: <파일명과 동일한 식별자>
title: <사람이 읽는 제목>
related: ["[[other-slug]]"]   # 양방향 링크 — A가 B를 링크하면 B에도 A 역링크
sources: ["claude_code:<날짜>/<세션>"]  # provenance: 이 내용이 어느 대화에서 왔는지
updated: YYYY-MM-DD
status: active|stale|review
---
```

## 작업: INGEST (새 대화/노트 통합)

1. 새 raw 조각을 읽고, **관련된 기존 페이지를 먼저 찾는다** (이름 매칭 + 의미 유사 + 링크 이웃).
2. **새 페이지를 함부로 만들지 말고**, 해당하는 기존 페이지를 **갱신**한다 (integrate-not-index).
3. 정말 새로운 엔티티/개념이면 새 페이지를 만든다.
4. 관련 페이지끼리 `[[slug]]`로 양방향 링크한다.
5. 갱신한 페이지의 `updated`와 `sources`를 채운다.

## 작업: QUERY (질문 답변)

1. wiki 페이지에서 근거를 찾아 답한다 (raw가 아니라 정제된 페이지 우선).
2. 각 주장에 `[[페이지]]`로 출처를 단다. 자료에 없는 내용은 추측하지 않는다.
3. 가치 있는 분석은 `Insights/`에 새 페이지로 남긴다 (write-back).

## 작업: LINT (정리)

- **자동 수정(구조)**: 끊긴 역링크 보강, 고아 페이지를 `index.md`에 연결, 죽은 `[[링크]]` 정리.
- **사람 검토 큐(진실)**: 사실 모순·낡음 의심·병합 후보는 `index.md` 검토 큐에 올린다. 임의로 진위를 단정하지 않는다.
"""


def schema_path(*, vault_path: Path | None = None) -> Path:
    """SCHEMA.md 경로 (vault 루트)."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / SCHEMA_FILENAME


def write_schema(*, vault_path: Path | None = None) -> Path:
    """SCHEMA.md를 템플릿으로 (재)작성. 기존 파일 덮어씀."""
    path = schema_path(vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SCHEMA_TEMPLATE, encoding="utf-8")
    return path


def ensure_schema(*, vault_path: Path | None = None) -> Path:
    """SCHEMA.md가 없을 때만 작성. 사용자 편집 보존."""
    path = schema_path(vault_path=vault_path)
    if not path.is_file():
        write_schema(vault_path=vault_path)
    return path
```

`wiki/__init__.py`의 import/`__all__`에 추가:

```python
from synapse_memory.wiki.schema import (
    SCHEMA_FILENAME,
    ensure_schema,
    schema_path,
    write_schema,
)
```
(`__all__`에도 `"SCHEMA_FILENAME"`, `"ensure_schema"`, `"schema_path"`, `"write_schema"` 추가)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_wiki_schema.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/synapse_memory/wiki/schema.py src/synapse_memory/wiki/__init__.py tests/test_wiki_schema.py
git commit -m "feat(wiki): add SCHEMA.md template + writer"
```

---

## Task 6: 전체 스위트 회귀 확인

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -q`
Expected: PASS — 기존 테스트 + 신규 `test_wiki_page.py`/`test_wiki_schema.py`/`test_config_maintenance.py` 모두 통과. (apfel/redaction 테스트는 아직 존재하며 통과해야 함 — P0는 삭제하지 않음.)

- [ ] **Step 2: Lint/type 확인 (있으면)**

Run: `uv run ruff check src/synapse_memory/wiki src/synapse_memory/config.py`
Expected: 통과 (위반 시 수정).

- [ ] **Step 3: Commit (필요 시 lint 수정만)**

```bash
git add -A
git commit -m "chore(wiki): satisfy lint for wiki foundation" || echo "no changes"
```

---

## Self-Review (작성자 체크리스트 결과)

- **Spec coverage:** 본 플랜은 spec 019의 L1 페이지 모델(§5 frontmatter, 6타입), L2 `SCHEMA.md`(§3, R4 vault 루트), 유지엔진/유휴 config(D1/D2/D3)를 구현. ingest/query/watch/lint/backfill은 의도적으로 P1~P5로 분리(범위 메모 명시). 갭 없음.
- **Placeholder scan:** "TODO"/"적절히 처리" 등 없음. 모든 코드·명령·기대출력 구체화됨.
- **Type consistency:** `WikiPage`(type/slug/title/related: tuple/sources: tuple/updated/status/body)가 Task 2~4에서 일관. `page_dir(page_type, *, vault_path, when)` 시그니처가 `page_path`/`load_page`/`list_pages`에서 일관. config `maintenance.engine`/`idle_minutes`, `vault_folders.wiki.*` 명칭이 Task 1 테스트와 일치.

> 검증 가정: ① `get_config(refresh=True)`가 `SYNAPSE_CONFIG_PATH` 환경변수를 본다는 전제는 Task 1 Step 2에서 확인 후 필요 시 테스트 조정. ② 프로젝트가 `uv run pytest`/`ruff`를 쓴다는 전제(미사용 시 `pytest`/프로젝트 표준으로 치환).
