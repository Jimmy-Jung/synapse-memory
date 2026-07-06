"""WikiPage 모델 round-trip + 검증."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from synapse_memory.wiki.page import (
    WikiPage,
    extract_wikilinks,
    list_pages,
    load_page,
    page_dir,
    parse_page,
    save_page,
    serialize_page,
    slugify,
    with_related,
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


def test_parse_null_updated_and_status_fall_back() -> None:
    text = "---\ntype: concept\nslug: x\ntitle: X\nupdated:\nstatus:\n---\n\nbody"
    page = parse_page(text)
    assert page.updated == ""
    assert page.status == "active"


def test_parse_invalid_date_raises_valueerror() -> None:
    text = "---\ntype: concept\nslug: x\ntitle: X\nupdated: 2026-13-40\n---\n\nbody"
    with pytest.raises(ValueError, match="파싱 실패"):
        parse_page(text)


def test_all_valid_types_round_trip() -> None:
    from synapse_memory.wiki.page import VALID_TYPES
    for t in VALID_TYPES:
        page = WikiPage(type=t, slug="s", title="T", body="b")
        assert parse_page(serialize_page(page)) == page


def test_slugify_korean_and_spaces() -> None:
    assert slugify("Synapse Memory") == "synapse-memory"
    assert slugify("이력서 작성") == "이력서-작성"
    assert slugify("  !!  ") == "untitled"


def test_page_dir_by_type(tmp_path: Path) -> None:
    assert page_dir("project", vault_path=tmp_path) == tmp_path / "Entities/Projects"
    assert page_dir("company", vault_path=tmp_path) == tmp_path / "Entities/Companies"
    assert page_dir("concept", vault_path=tmp_path) == tmp_path / "Concepts"
    assert page_dir("profile", vault_path=tmp_path) == tmp_path / "Profile"
    assert page_dir("log", vault_path=tmp_path, when=date(2026, 7, 6)) == tmp_path / "Logs" / "2026" / "07"


def test_page_dir_insight_uses_year_month(tmp_path: Path) -> None:
    import datetime

    d = page_dir("insight", vault_path=tmp_path, when=datetime.date(2026, 6, 14))
    assert d == tmp_path / "Insights" / "2026" / "06"


def test_page_dir_rejects_unknown_type(tmp_path: Path) -> None:
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


def test_load_page_rejects_path_traversal(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="slug"):
        load_page("concept", "../../etc/passwd", vault_path=tmp_path)


def test_parse_rejects_quoted_bad_date() -> None:
    text = '---\ntype: concept\nslug: x\ntitle: X\nupdated: "2026-99-99"\n---\n\nbody'
    with pytest.raises(ValueError, match="updated"):
        parse_page(text)


def test_extract_wikilinks() -> None:
    body = "관련: [[rag]] 와 [[obsidian]], 그리고 또 [[rag]].\n"
    assert extract_wikilinks(body) == ["rag", "obsidian"]


def test_extract_wikilinks_strips_alias() -> None:
    assert extract_wikilinks("[[rag|검색증강생성]] 참고") == ["rag"]


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


def test_with_related_dedupes_by_target_ignoring_alias() -> None:
    page = WikiPage(type="concept", slug="x", title="X", related=("[[a|A Title]]",))
    # 같은 대상 a를 별칭 없이 추가 시도 → 중복 안 만듦
    assert with_related(page, "[[a]]").related == ("[[a|A Title]]",)
    # 다른 대상은 정상 추가
    assert with_related(page, "[[b]]").related == ("[[a|A Title]]", "[[b]]")
